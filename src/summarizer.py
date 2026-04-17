"""
Academic paper summarization.

Generates structured summaries focusing on:
- Research question(s)
- Theoretical framework
- Data sources
- Methods / analytical strategy
- Key findings
- Contribution

Supports two backends:
- "claude": Uses Anthropic Claude API for high-quality summaries
- "local": Rule-based extraction (no API key needed)
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, SUMMARY_DIR, SUMMARIZER_BACKEND
from src.extractor import ExtractedPaper, get_relevant_text
from src.scraper import Article

logger = logging.getLogger(__name__)

SUMMARY_PROMPT_ZH = """\
你是一位社會學學術論文分析專家。請閱讀以下學術論文的內容，並以繁體中文產出結構化的摘要。

論文基本資訊：
- 標題：{title}
- 作者：{authors}
- 期刊：{journal}
- 卷期：Vol. {volume}, No. {issue}
- 出版日期：{pub_date}

請根據以下架構進行分析（每一項都必須回答）：

## 1. 研究問題 (Research Question)
本文要回答什麼核心問題？有哪些具體的子問題？

## 2. 理論框架 (Theoretical Framework)
作者使用了什麼理論或概念框架？如何與既有文獻對話？有何理論創新？

## 3. 資料來源 (Data)
使用了什麼資料？包括：資料名稱、來源、時間範圍、樣本大小、分析單位等。

## 4. 研究方法 (Methods)
使用了什麼分析方法？包括：統計模型、質性方法、因果推論策略等。

## 5. 主要發現 (Key Findings)
最重要的研究發現是什麼？請條列說明。

## 6. 學術貢獻 (Contribution)
本文對該領域的主要貢獻為何？有何政策意涵？

---
論文內容：
{text}
"""

SUMMARY_PROMPT_EN = """\
You are an expert in analyzing academic sociology papers. Read the following paper content and produce a structured summary.

Paper metadata:
- Title: {title}
- Authors: {authors}
- Journal: {journal}
- Volume/Issue: Vol. {volume}, No. {issue}
- Publication date: {pub_date}

Analyze using the following structure (all sections required):

## 1. Research Question
What is the core question this paper addresses? What specific sub-questions does it examine?

## 2. Theoretical Framework
What theory or conceptual framework does the paper use? How does it engage with existing literature? What theoretical innovations does it propose?

## 3. Data
What data does it use? Include: dataset name, source, time period, sample size, unit of analysis.

## 4. Methods
What analytical methods are used? Include: statistical models, qualitative methods, causal inference strategies.

## 5. Key Findings
What are the most important findings? List them clearly.

## 6. Contribution
What is the paper's main contribution to the field? What policy implications does it suggest?

---
Paper content:
{text}
"""


@dataclass
class PaperSummary:
    title: str
    authors: list[str]
    doi: str
    journal: str
    volume: str
    issue: str
    publication_date: str
    research_question: str = ""
    theoretical_framework: str = ""
    data: str = ""
    methods: str = ""
    key_findings: str = ""
    contribution: str = ""
    raw_summary: str = ""


def summarize_with_claude(article: Article, paper: ExtractedPaper, lang: str = "zh") -> PaperSummary:
    """Summarize using Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return _empty_summary(article)

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set. Export it or use SUMMARIZER_BACKEND=local")
        return _empty_summary(article)

    text = get_relevant_text(paper, max_chars=28000)
    prompt_template = SUMMARY_PROMPT_ZH if lang == "zh" else SUMMARY_PROMPT_EN

    prompt = prompt_template.format(
        title=article.title,
        authors=", ".join(article.authors),
        journal=article.journal,
        volume=article.volume,
        issue=article.issue,
        pub_date=article.publication_date,
        text=text,
    )

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    logger.info(f"Sending to Claude for summarization: {article.title[:60]}...")
    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_summary = response.content[0].text
    except Exception as e:
        logger.error(f"Claude API error: {e}")
        return _empty_summary(article)

    summary = _parse_summary(article, raw_summary)
    return summary


def summarize_local(article: Article, paper: ExtractedPaper) -> PaperSummary:
    """
    Local rule-based summarization (no API needed).
    Extracts text directly from identified sections.
    """
    summary = PaperSummary(
        title=article.title,
        authors=article.authors,
        doi=article.doi,
        journal=article.journal,
        volume=article.volume,
        issue=article.issue,
        publication_date=article.publication_date,
    )

    sections = paper.sections

    # Abstract as a fallback overview
    abstract = sections.get("abstract", article.abstract)

    # Research question: look in abstract and introduction
    intro = sections.get("introduction", "")
    rq_sentences = _find_sentences_with_keywords(
        abstract + "\n" + intro,
        ["this paper", "this study", "we examine", "we investigate", "we ask",
         "this article", "research question", "how does", "how do",
         "whether", "the extent to which", "we argue", "we analyze"]
    )
    summary.research_question = "\n".join(rq_sentences[:5]) if rq_sentences else abstract[:500]

    # Theory: from theory/background section or introduction
    theory_text = sections.get("theory", sections.get("background", ""))
    if theory_text:
        summary.theoretical_framework = _truncate(theory_text, 800)
    else:
        theory_sentences = _find_sentences_with_keywords(
            intro,
            ["theory", "theoretical", "framework", "perspective", "argue that",
             "building on", "drawing on", "conceptual", "hypothesis"]
        )
        summary.theoretical_framework = "\n".join(theory_sentences[:5])

    # Data
    methods_text = sections.get("methods", sections.get("measures", ""))
    data_sentences = _find_sentences_with_keywords(
        methods_text,
        ["data", "dataset", "sample", "survey", "census", "panel",
         "respondent", "observation", "N =", "n =", "cases",
         "waves", "years", "period", "source"]
    )
    summary.data = "\n".join(data_sentences[:5]) if data_sentences else ""

    # Methods
    method_sentences = _find_sentences_with_keywords(
        methods_text,
        ["regression", "model", "method", "analysis", "estimate",
         "fixed effect", "instrumental", "difference-in-difference",
         "logistic", "OLS", "multilevel", "hierarchical", "propensity",
         "matching", "qualitative", "interview", "ethnograph",
         "content analysis", "network analysis", "causal"]
    )
    summary.methods = "\n".join(method_sentences[:5]) if method_sentences else ""

    # Findings: from results or discussion
    results_text = sections.get("results", sections.get("discussion", ""))
    finding_sentences = _find_sentences_with_keywords(
        results_text,
        ["find that", "results show", "results indicate", "evidence",
         "significant", "effect", "associated with", "relationship",
         "support", "consistent with", "contrary to", "suggest"]
    )
    summary.key_findings = "\n".join(finding_sentences[:5]) if finding_sentences else ""

    # Contribution: from conclusion
    conclusion = sections.get("conclusion", sections.get("discussion", ""))
    contrib_sentences = _find_sentences_with_keywords(
        conclusion,
        ["contribut", "implication", "advance", "extend", "novel",
         "first to", "policy", "future research", "limitation"]
    )
    summary.contribution = "\n".join(contrib_sentences[:5]) if contrib_sentences else ""

    summary.raw_summary = f"[Local extraction]\n\nAbstract: {abstract}"
    return summary


def _find_sentences_with_keywords(text: str, keywords: list[str]) -> list[str]:
    """Find sentences containing any of the given keywords."""
    if not text:
        return []
    sentences = re.split(r'(?<=[.!?])\s+', text)
    matched = []
    seen = set()
    for sent in sentences:
        sent = sent.strip()
        if not sent or len(sent) < 20:
            continue
        lower = sent.lower()
        if any(kw.lower() in lower for kw in keywords):
            if sent not in seen:
                matched.append(sent)
                seen.add(sent)
    return matched


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "..."


def _parse_summary(article: Article, raw_text: str) -> PaperSummary:
    """Parse the Claude-generated summary into structured fields."""
    summary = PaperSummary(
        title=article.title,
        authors=article.authors,
        doi=article.doi,
        journal=article.journal,
        volume=article.volume,
        issue=article.issue,
        publication_date=article.publication_date,
        raw_summary=raw_text,
    )

    section_map = {
        "研究問題": "research_question",
        "Research Question": "research_question",
        "理論框架": "theoretical_framework",
        "Theoretical Framework": "theoretical_framework",
        "資料來源": "data",
        "Data": "data",
        "研究方法": "methods",
        "Methods": "methods",
        "主要發現": "key_findings",
        "Key Findings": "key_findings",
        "學術貢獻": "contribution",
        "Contribution": "contribution",
    }

    # Parse markdown sections
    current_field = None
    current_content: list[str] = []

    for line in raw_text.split("\n"):
        matched = False
        for header, field_name in section_map.items():
            if header in line and line.strip().startswith("#"):
                # Save previous section
                if current_field and current_content:
                    setattr(summary, current_field, "\n".join(current_content).strip())
                current_field = field_name
                current_content = []
                matched = True
                break
        if not matched and current_field:
            current_content.append(line)

    # Save the last section
    if current_field and current_content:
        setattr(summary, current_field, "\n".join(current_content).strip())

    return summary


def _empty_summary(article: Article) -> PaperSummary:
    return PaperSummary(
        title=article.title,
        authors=article.authors,
        doi=article.doi,
        journal=article.journal,
        volume=article.volume,
        issue=article.issue,
        publication_date=article.publication_date,
    )


def summarize(article: Article, paper: ExtractedPaper, lang: str = "zh") -> PaperSummary:
    """Summarize a paper using the configured backend."""
    backend = SUMMARIZER_BACKEND
    if backend == "claude":
        return summarize_with_claude(article, paper, lang=lang)
    else:
        return summarize_local(article, paper)


def save_summary(summary: PaperSummary, output_dir: Path = SUMMARY_DIR) -> Path:
    """Save summary as both JSON and readable Markdown."""
    doi_suffix = summary.doi.split("/")[-1] if summary.doi else "unknown"
    safe_title = re.sub(r'[^\w\s-]', '', summary.title)
    safe_title = re.sub(r'\s+', '_', safe_title.strip())[:60]

    # Save JSON
    json_path = output_dir / f"{doi_suffix}.json"
    json_path.write_text(json.dumps(asdict(summary), ensure_ascii=False, indent=2), encoding="utf-8")

    # Save Markdown
    md_path = output_dir / f"{doi_suffix}.md"
    md_content = _format_summary_markdown(summary)
    md_path.write_text(md_content, encoding="utf-8")

    logger.info(f"Saved summary: {md_path.name}")
    return md_path


def _format_summary_markdown(s: PaperSummary) -> str:
    """Format summary as a readable Markdown document."""
    authors_str = ", ".join(s.authors) if s.authors else "N/A"
    return f"""# {s.title}

**Authors:** {authors_str}
**Journal:** {s.journal} | Vol. {s.volume}, No. {s.issue}
**DOI:** {s.doi}
**Date:** {s.publication_date}

---

## 1. 研究問題 (Research Question)

{s.research_question or "N/A"}

## 2. 理論框架 (Theoretical Framework)

{s.theoretical_framework or "N/A"}

## 3. 資料來源 (Data)

{s.data or "N/A"}

## 4. 研究方法 (Methods)

{s.methods or "N/A"}

## 5. 主要發現 (Key Findings)

{s.key_findings or "N/A"}

## 6. 學術貢獻 (Contribution)

{s.contribution or "N/A"}
"""
