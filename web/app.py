"""
Flask web application for the Journal PDF Scraper & Summarizer.

Provides a UI to:
- View configured journals
- Browse articles fetched from each journal
- View structured summaries
- Trigger scraping / downloading / summarization
- Monitor pipeline progress
"""

import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path

import markdown
from flask import Flask, jsonify, render_template, request

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Force UTF-8 for stdout/stderr on Windows (default cp950/cp1252 breaks on
# non-ASCII log output like German/French author names).
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import JOURNALS, OUTPUT_DIR, PDF_DIR, SUMMARY_DIR
from src.scraper import Article, fetch_latest_issue, save_metadata
from src.downloader import download_all
from src.extractor import extract_text_from_pdf
from src.summarizer import save_summary, summarize

logger = logging.getLogger(__name__)

app = Flask(__name__)

# ── Pipeline state (shared across threads) ────────────────────────────────
pipeline_state = {
    "running": False,
    "journal": None,
    "phase": "",          # "fetching" / "downloading" / "summarizing" / "done" / "error"
    "progress": 0,        # 0-100
    "total_articles": 0,
    "current_article": 0,
    "current_title": "",
    "log": [],            # recent log messages
    "error": None,
}
state_lock = threading.Lock()


def _update_state(**kwargs):
    with state_lock:
        pipeline_state.update(kwargs)


def _add_log(msg: str):
    with state_lock:
        pipeline_state["log"].append(msg)
        if len(pipeline_state["log"]) > 100:
            pipeline_state["log"] = pipeline_state["log"][-50:]


# ── Data loading helpers ──────────────────────────────────────────────────
def load_metadata(journal_key: str) -> list[dict]:
    """Load article metadata from JSON."""
    path = OUTPUT_DIR / f"{journal_key}_metadata.json"
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return []
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning(f"Failed to parse metadata: {path}")
        return []


def load_summary(journal_key: str, doi_suffix: str) -> dict | None:
    """Load a single article summary."""
    json_path = SUMMARY_DIR / journal_key / f"{doi_suffix}.json"
    if not json_path.exists():
        return None
    try:
        text = json_path.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning(f"Failed to parse summary: {json_path}")
        return None


def load_summary_md(journal_key: str, doi_suffix: str) -> str | None:
    """Load summary as rendered HTML from markdown."""
    md_path = SUMMARY_DIR / journal_key / f"{doi_suffix}.md"
    if not md_path.exists():
        return None
    try:
        md_text = md_path.read_text(encoding="utf-8")
        return markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    except Exception:
        return None


def get_article_status(journal_key: str, doi: str) -> dict:
    """Check PDF download and summary status for an article."""
    doi_suffix = doi.split("/")[-1] if doi else ""
    pdf_dir = PDF_DIR / journal_key

    has_pdf = False
    if pdf_dir.exists():
        has_pdf = any(pdf_dir.glob(f"{doi_suffix}*"))

    has_summary = False
    summary_path = SUMMARY_DIR / journal_key / f"{doi_suffix}.json"
    has_summary = summary_path.exists()

    return {"has_pdf": has_pdf, "has_summary": has_summary}


# ── Background pipeline runner ────────────────────────────────────────────
def run_pipeline_bg(journal_key: str, backend: str = "claude", lang: str = "zh"):
    """Run the full pipeline in a background thread."""
    import config
    config.SUMMARIZER_BACKEND = backend

    try:
        # Phase 1: Fetch metadata
        _update_state(
            running=True, journal=journal_key, phase="fetching",
            progress=5, current_title="正在從 API 取得文章列表...",
            error=None, log=[]
        )
        _add_log(f"開始抓取 {JOURNALS[journal_key]['name']} 最新文章...")

        articles = fetch_latest_issue(journal_key, max_articles=20)
        if not articles:
            _update_state(phase="error", running=False, error="未找到任何文章，請檢查網路連線。")
            return

        save_metadata(articles, journal_key)
        _update_state(
            total_articles=len(articles), progress=15,
            phase="downloading"
        )
        _add_log(f"找到 {len(articles)} 篇文章，開始下載 PDF...")

        # Phase 2: Download PDFs
        journal_pdf_dir = PDF_DIR / journal_key
        journal_pdf_dir.mkdir(exist_ok=True)

        downloaded = {}
        for i, article in enumerate(articles, 1):
            pct = 15 + int(45 * i / len(articles))
            _update_state(
                current_article=i, progress=pct,
                current_title=f"下載中：{article.title[:50]}..."
            )
            _add_log(f"[{i}/{len(articles)}] 下載：{article.title[:60]}")

            from src.downloader import download_pdf
            path = download_pdf(article, output_dir=journal_pdf_dir)
            if path:
                downloaded[article.doi] = path
            time.sleep(1)

        _add_log(f"下載完成：{len(downloaded)}/{len(articles)} 篇")

        # Phase 3: Summarize
        _update_state(phase="summarizing", progress=65)
        _add_log("開始產生摘要...")

        journal_summary_dir = SUMMARY_DIR / journal_key
        journal_summary_dir.mkdir(exist_ok=True)

        summarized = 0
        for i, article in enumerate(articles, 1):
            pdf_path = downloaded.get(article.doi)
            if not pdf_path:
                continue

            doi_suffix = article.doi.split("/")[-1] if article.doi else ""
            if (journal_summary_dir / f"{doi_suffix}.json").exists():
                summarized += 1
                continue

            pct = 65 + int(30 * i / len(articles))
            _update_state(
                current_article=i, progress=pct,
                current_title=f"摘要中：{article.title[:50]}..."
            )
            _add_log(f"[{i}/{len(articles)}] 摘要：{article.title[:60]}")

            paper = extract_text_from_pdf(pdf_path)
            if paper.full_text:
                summary = summarize(article, paper, lang=lang)
                save_summary(summary, output_dir=journal_summary_dir)
                summarized += 1
                if backend == "claude":
                    time.sleep(2)

        _update_state(phase="done", progress=100, running=False,
                      current_title="完成！")
        _add_log(f"全部完成！共產生 {summarized} 篇摘要。")

    except Exception as e:
        logger.exception("Pipeline error")
        _update_state(phase="error", running=False, error=str(e))
        _add_log(f"錯誤：{e}")


# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    """Dashboard: list all journals with article counts."""
    journals_info = []
    for key, info in JOURNALS.items():
        articles = load_metadata(key)
        summary_dir = SUMMARY_DIR / key
        summary_count = len(list(summary_dir.glob("*.json"))) if summary_dir.exists() else 0
        pdf_dir = PDF_DIR / key
        pdf_count = len(list(pdf_dir.glob("*.pdf"))) if pdf_dir.exists() else 0

        journals_info.append({
            "key": key,
            "name": info["name"],
            "issn": info["issn"],
            "publisher": info["publisher"],
            "article_count": len(articles),
            "pdf_count": pdf_count,
            "summary_count": summary_count,
        })

    return render_template("index.html", journals=journals_info)


@app.route("/journal/<journal_key>")
def journal_detail(journal_key: str):
    """Article list for a specific journal."""
    if journal_key not in JOURNALS:
        return "Journal not found", 404

    journal = JOURNALS[journal_key]
    articles = load_metadata(journal_key)

    # Enrich with status
    for a in articles:
        status = get_article_status(journal_key, a.get("doi", ""))
        a["has_pdf"] = status["has_pdf"]
        a["has_summary"] = status["has_summary"]
        a["doi_suffix"] = a.get("doi", "").split("/")[-1] if a.get("doi") else ""

    return render_template("journal.html",
                           journal_key=journal_key,
                           journal=journal,
                           articles=articles)


@app.route("/article/<journal_key>/<doi_suffix>")
def article_detail(journal_key: str, doi_suffix: str):
    """Article detail page with summary."""
    if journal_key not in JOURNALS:
        return "Journal not found", 404

    journal = JOURNALS[journal_key]
    articles = load_metadata(journal_key)

    # Find the article
    article = None
    for a in articles:
        if a.get("doi", "").split("/")[-1] == doi_suffix:
            article = a
            break

    if not article:
        return "Article not found", 404

    # Load summary
    summary_data = load_summary(journal_key, doi_suffix)
    summary_html = load_summary_md(journal_key, doi_suffix)
    status = get_article_status(journal_key, article.get("doi", ""))

    return render_template("article.html",
                           journal_key=journal_key,
                           journal=journal,
                           article=article,
                           summary=summary_data,
                           summary_html=summary_html,
                           status=status)


# ── API routes ────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def api_run():
    """Trigger the full pipeline for a journal."""
    data = request.json or {}
    journal_key = data.get("journal", "asr")
    backend = data.get("backend", "claude")
    lang = data.get("lang", "zh")

    if journal_key not in JOURNALS:
        return jsonify({"error": "Unknown journal"}), 400

    with state_lock:
        if pipeline_state["running"]:
            return jsonify({"error": "Pipeline already running"}), 409

    thread = threading.Thread(
        target=run_pipeline_bg,
        args=(journal_key, backend, lang),
        daemon=True,
    )
    thread.start()
    return jsonify({"status": "started", "journal": journal_key})


@app.route("/api/status")
def api_status():
    """Get current pipeline status."""
    with state_lock:
        return jsonify(dict(pipeline_state))


@app.route("/api/articles/<journal_key>")
def api_articles(journal_key: str):
    """Get article list as JSON."""
    articles = load_metadata(journal_key)
    for a in articles:
        status = get_article_status(journal_key, a.get("doi", ""))
        a.update(status)
    return jsonify(articles)


@app.route("/api/summary/<journal_key>/<doi_suffix>")
def api_summary(journal_key: str, doi_suffix: str):
    """Get a single summary as JSON."""
    data = load_summary(journal_key, doi_suffix)
    if data:
        return jsonify(data)
    return jsonify({"error": "Summary not found"}), 404


# ── App runner ────────────────────────────────────────────────────────────
def create_app():
    return app


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.run(host="0.0.0.0", port=5000, debug=True)
