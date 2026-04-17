#!/usr/bin/env python3
"""
Journal PDF Scraper & Summarizer

抓取學術期刊最新一期的 PDF，並自動進行結構化摘要。
Scrape academic journal PDFs and generate structured summaries.

Usage:
    # Run once for a specific journal
    python main.py run --journal asr

    # Run once, local summarization (no API key needed)
    python main.py run --journal asr --backend local

    # Run once, Chinese summaries with Claude API
    python main.py run --journal asr --backend claude --lang zh

    # List articles only (no download or summarization)
    python main.py list --journal asr

    # Download PDFs only (no summarization)
    python main.py download --journal asr

    # Start scheduler (periodic scraping)
    python main.py schedule --journal asr --interval 168

    # Show configured journals
    python main.py journals
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Force UTF-8 for stdout/stderr on Windows (default is cp950/cp1252)
# to avoid UnicodeEncodeError when printing non-ASCII characters.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import schedule as schedule_lib

from config import (
    JOURNALS,
    LOG_DIR,
    OUTPUT_DIR,
    PDF_DIR,
    SCHEDULE_INTERVAL_HOURS,
    SUMMARY_DIR,
)
from src.downloader import download_all
from src.extractor import extract_text_from_pdf
from src.scraper import Article, fetch_latest_issue, save_metadata
from src.summarizer import save_summary, summarize

# ── Logging setup ─────────────────────────────────────────────────────────
def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    # Stream handler that tolerates encoding errors on Windows consoles
    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(level)
    # Clear any pre-existing handlers from basicConfig
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(stream)

    # Also log to file (always UTF-8)
    file_handler = logging.FileHandler(LOG_DIR / "scraper.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt))
    root.addHandler(file_handler)


logger = logging.getLogger(__name__)


# ── Core pipeline ─────────────────────────────────────────────────────────
def run_pipeline(
    journal_key: str,
    backend: str = "claude",
    lang: str = "zh",
    skip_download: bool = False,
    skip_summary: bool = False,
    max_articles: int = 20,
):
    """Run the full scrape -> download -> summarize pipeline."""
    logger.info(f"{'='*60}")
    logger.info(f"Starting pipeline for: {JOURNALS[journal_key]['name']}")
    logger.info(f"Backend: {backend} | Language: {lang}")
    logger.info(f"{'='*60}")

    # Override summarizer backend
    import config
    config.SUMMARIZER_BACKEND = backend

    # Step 1: Fetch article metadata
    logger.info("Step 1: Fetching article metadata...")
    articles = fetch_latest_issue(journal_key, max_articles=max_articles)

    if not articles:
        logger.warning("No articles found. Check network connection and API availability.")
        return

    # Save metadata
    meta_path = save_metadata(articles, journal_key)
    logger.info(f"Found {len(articles)} articles. Metadata saved to {meta_path}")

    # Print article list
    print(f"\n{'='*60}")
    print(f"  {JOURNALS[journal_key]['name']}")
    print(f"  Found {len(articles)} articles")
    print(f"{'='*60}\n")
    for i, a in enumerate(articles, 1):
        vol_info = f"Vol.{a.volume}" if a.volume else ""
        if a.issue:
            vol_info += f" No.{a.issue}"
        print(f"  {i:2d}. {a.title[:70]}")
        print(f"      Authors: {', '.join(a.authors[:3])}")
        print(f"      DOI: {a.doi} | {vol_info} | {a.publication_date}")
        print()

    if skip_download and skip_summary:
        return

    # Step 2: Download PDFs
    if not skip_download:
        logger.info("Step 2: Downloading PDFs...")
        journal_pdf_dir = PDF_DIR / journal_key
        journal_pdf_dir.mkdir(exist_ok=True)
        downloaded = download_all(articles, output_dir=journal_pdf_dir)
        logger.info(f"Downloaded {len(downloaded)} PDFs")
    else:
        # Check for existing PDFs
        journal_pdf_dir = PDF_DIR / journal_key
        downloaded = {}
        for a in articles:
            pdf_path = journal_pdf_dir / a.pdf_filename
            if pdf_path.exists():
                downloaded[a.doi] = pdf_path

    if skip_summary:
        return

    # Step 3: Extract text and summarize
    logger.info("Step 3: Extracting text and generating summaries...")
    journal_summary_dir = SUMMARY_DIR / journal_key
    journal_summary_dir.mkdir(exist_ok=True)

    summaries_generated = 0
    for article in articles:
        pdf_path = downloaded.get(article.doi)
        if not pdf_path:
            logger.info(f"Skipping (no PDF): {article.title[:50]}")
            continue

        # Check if summary already exists
        doi_suffix = article.doi.split("/")[-1] if article.doi else "unknown"
        summary_json = journal_summary_dir / f"{doi_suffix}.json"
        if summary_json.exists():
            logger.info(f"Summary already exists: {doi_suffix}")
            summaries_generated += 1
            continue

        # Extract text
        paper = extract_text_from_pdf(pdf_path)
        if not paper.full_text:
            logger.warning(f"No text extracted from: {pdf_path.name}")
            continue

        # Summarize
        summary = summarize(article, paper, lang=lang)
        save_summary(summary, output_dir=journal_summary_dir)
        summaries_generated += 1

        # Be polite to API
        if backend == "claude":
            time.sleep(2)

    logger.info(f"Generated {summaries_generated} summaries")
    print(f"\nDone! {summaries_generated} summaries saved to {journal_summary_dir}")


# ── CLI commands ──────────────────────────────────────────────────────────
def cmd_run(args):
    run_pipeline(
        journal_key=args.journal,
        backend=args.backend,
        lang=args.lang,
        max_articles=args.max,
    )


def cmd_list(args):
    run_pipeline(
        journal_key=args.journal,
        skip_download=True,
        skip_summary=True,
        max_articles=args.max,
    )


def cmd_download(args):
    run_pipeline(
        journal_key=args.journal,
        skip_summary=True,
        max_articles=args.max,
    )


def cmd_debug_rss(args):
    """Test each configured RSS URL and report what was received."""
    import requests
    from config import JOURNALS, REQUEST_TIMEOUT
    from src.scraper import fetch_articles_rss

    journal = JOURNALS.get(args.journal)
    if not journal:
        print(f"Unknown journal: {args.journal}")
        return

    urls = journal.get("rss_urls") or [journal.get("rss_url")]
    urls = [u for u in urls if u]

    if not urls:
        print("No RSS URLs configured.")
        return

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
    }

    print(f"\n{'='*70}")
    print(f"  RSS Diagnostics — {journal['name']}")
    print(f"{'='*70}\n")

    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] GET {url}")
        try:
            r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            print(f"    HTTP {r.status_code}")
            print(f"    Content-Type: {r.headers.get('Content-Type', '?')}")
            print(f"    Size: {len(r.content)} bytes")
            snippet = r.content[:300].decode("utf-8", errors="replace")
            print(f"    First 300 chars:")
            print(f"    {snippet!r}")
        except requests.RequestException as e:
            print(f"    REQUEST FAILED: {e}")
        print()

    # Now try the full parser
    print("─" * 70)
    print("Running full RSS fetcher (with multi-URL fallback)...")
    print("─" * 70)
    articles = fetch_articles_rss(args.journal)
    print(f"\nResult: {len(articles)} articles parsed\n")
    for i, a in enumerate(articles[:5], 1):
        print(f"  {i}. {a.title[:70]}")
        print(f"     DOI: {a.doi}")
        print(f"     Authors: {', '.join(a.authors[:3])}")
        print(f"     Vol/Issue: {a.volume}/{a.issue} — {a.publication_date}")
        print()
    if len(articles) > 5:
        print(f"  ... and {len(articles) - 5} more")


def cmd_schedule(args):
    journal_key = args.journal
    interval = args.interval or SCHEDULE_INTERVAL_HOURS

    logger.info(f"Starting scheduler: every {interval} hours for {journal_key}")
    print(f"Scheduler started. Will run every {interval} hours.")
    print(f"Press Ctrl+C to stop.\n")

    # Run once immediately
    run_pipeline(
        journal_key=journal_key,
        backend=args.backend,
        lang=args.lang,
    )

    # Schedule future runs
    schedule_lib.every(interval).hours.do(
        run_pipeline,
        journal_key=journal_key,
        backend=args.backend,
        lang=args.lang,
    )

    try:
        while True:
            schedule_lib.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nScheduler stopped.")


def cmd_journals(args):
    print("\nConfigured journals:\n")
    for key, info in JOURNALS.items():
        print(f"  {key:10s}  {info['name']}")
        print(f"             ISSN: {info['issn']} | Publisher: {info['publisher']}")
        if info.get("toc_url"):
            print(f"             TOC:  {info['toc_url']}")
        rss = info.get("rss_urls") or ([info["rss_url"]] if info.get("rss_url") else [])
        for u in rss:
            print(f"             RSS:  {u}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Journal PDF Scraper & Summarizer - 學術期刊 PDF 抓取與摘要工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run
    p_run = subparsers.add_parser("run", help="Full pipeline: fetch → download → summarize")
    p_run.add_argument("-j", "--journal", required=True, choices=JOURNALS.keys(),
                       help="Journal key (e.g., asr)")
    p_run.add_argument("-b", "--backend", default="claude", choices=["claude", "local"],
                       help="Summarization backend (default: claude)")
    p_run.add_argument("-l", "--lang", default="zh", choices=["zh", "en"],
                       help="Summary language (default: zh = Traditional Chinese)")
    p_run.add_argument("-m", "--max", type=int, default=20,
                       help="Max articles to process (default: 20)")
    p_run.set_defaults(func=cmd_run)

    # list
    p_list = subparsers.add_parser("list", help="List articles only (no download)")
    p_list.add_argument("-j", "--journal", required=True, choices=JOURNALS.keys())
    p_list.add_argument("-m", "--max", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    # download
    p_dl = subparsers.add_parser("download", help="Fetch metadata and download PDFs only")
    p_dl.add_argument("-j", "--journal", required=True, choices=JOURNALS.keys())
    p_dl.add_argument("-m", "--max", type=int, default=20)
    p_dl.set_defaults(func=cmd_download)

    # schedule
    p_sched = subparsers.add_parser("schedule", help="Run periodically on a schedule")
    p_sched.add_argument("-j", "--journal", required=True, choices=JOURNALS.keys())
    p_sched.add_argument("-i", "--interval", type=int, default=None,
                         help=f"Interval in hours (default: {SCHEDULE_INTERVAL_HOURS})")
    p_sched.add_argument("-b", "--backend", default="claude", choices=["claude", "local"])
    p_sched.add_argument("-l", "--lang", default="zh", choices=["zh", "en"])
    p_sched.set_defaults(func=cmd_schedule)

    # journals
    p_journals = subparsers.add_parser("journals", help="List configured journals")
    p_journals.set_defaults(func=cmd_journals)

    # debug-rss
    p_rss = subparsers.add_parser("debug-rss", help="Diagnose RSS feed fetching")
    p_rss.add_argument("-j", "--journal", required=True, choices=JOURNALS.keys())
    p_rss.set_defaults(func=cmd_debug_rss)

    args = parser.parse_args()
    setup_logging(verbose=getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
