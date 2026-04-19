"""
Academic paper summarization.

Generates structured 8-section summaries covering:
1. Research Question
2. Theoretical Context (文獻對話)
3. Theoretical Framework
4. Data Source
5. Model & Methodology
6. Findings / Results
7. Conclusion & Contribution
8. Limitations & Future Research

Supported backends (set via SUMMARIZER_BACKEND env var):
- "openai" — OpenAI GPT (default; requires OPENAI_API_KEY)
- "claude" — Anthropic Claude (requires ANTHROPIC_API_KEY)
- "local"  — rule-based extraction (no API key needed)
"""

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from config import (
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    SUMMARY_DIR,
    SUMMARIZER_BACKEND,
)
from src.extractor import ExtractedPaper, get_relevant_text
from src.scraper import Article

logger = logging.getLogger(__name__)

# ── Prompt templates ──────────────────────────────────────────────────────

SUMMARY_PROMPT_ZH = """\
請閱讀以下學術論文內容，並以嚴謹且結構化的方式進行分析與摘要。請避免空泛描述，盡可能使用論文中的實際概念與術語。

重要格式要求：每一節的內容都必須同時以「繁體中文」和「English」兩種語言並列呈現。請先寫中文，再寫英文，以「---」分隔，如下列範例所示：

範例格式：
## 1. 研究問題（Research Question）
**【中文】**
- 核心問題：收入不平等如何影響政治參與？
- 研究動機：民主社會的不平等加劇，引發對政治代表性的關注。

**【English】**
- Core question: How does income inequality affect political participation?
- Motivation: Rising inequality in democracies raises concerns about political representation.

（以下每一節都請嚴格依照此「中文 → English」並列格式呈現。）

---

論文基本資訊：
- 標題：{title}
- 作者：{authors}
- 期刊：{journal}
- 卷期：Vol. {volume}, No. {issue}
- 出版日期：{pub_date}

請依照以下架構輸出（每一節都必須中英文並列）：

## 1. 研究問題（Research Question）
- 作者試圖解決的核心問題是什麼？
- 研究動機與背景為何？

## 2. 對話的理論脈絡（Theoretical Context / Literature Conversation）
- 本研究主要回應或延伸哪些學術文獻或理論？
- 在既有研究中所處的位置為何（補充、挑戰或整合）？

## 3. 理論架構（Theoretical Framework）
- 作者採用哪些核心理論或概念？
- 各概念之間的關係為何？

## 4. 資料來源（Data Source）
- 使用什麼資料（例如：問卷、訪談、次級資料、實驗資料等）？
- 樣本來源、數量與特性為何？

## 5. 研究模型與方法（Model & Methodology）
- 使用何種研究方法（質化、量化或混合）？
- 具體分析工具或模型為何（例如：回歸分析、SEM、case study 等）？
- 自變項（independent variables）、依變項（dependent variables）、控制變項、或工具變項為何？

## 6. 模型結果（Findings / Results）
- 主要實證結果是什麼？
- 哪些假設被支持或不被支持？

## 7. 重要結論與貢獻（Conclusion & Contribution）
- 本研究的主要結論為何？
- 對理論或實務的貢獻是什麼？

## 8. 限制與未來研究（Limitations & Future Research）
- 作者提到哪些限制？
- 未來研究方向為何？

## 9. R 模擬重製程式碼（R Simulation Code）

**僅針對量化研究**：如果本論文是**純量化研究**或**量化＋質化混合研究**，請根據量化部分產出一段**完整且可直接執行**的 R 程式碼。

### 模擬數據要求：
- 盡可能涵蓋**論文中提到的所有變項**，包括但不限於：
  - 依變項（dependent variables）
  - 核心自變項（key independent variables）
  - 控制變項（control variables）：如性別、年齡、教育程度、收入、種族、地區等
  - 工具變項（instrumental variables，若有使用）
  - 固定效應識別變項（如個體 ID、時間、地區等）
  - 交互作用項（interaction terms，若有）
  - 權重變項（sampling weights，若有）
- 變項名稱盡量與論文中使用的名稱一致
- 樣本量 (N) 盡量符合論文描述
- 依變項和自變項的分佈類型要合理（如連續、二元、計數、有序等）
- 使用 `set.seed()` 確保可重複

### 統計模型要求：
- 使用論文中**實際採用**的統計模型與 R 函數，例如：
  - OLS 回歸 → `lm()`
  - Logistic 回歸 → `glm(..., family = binomial)`
  - Negative binomial → `MASS::glm.nb()`
  - 個體固定效應 → `plm::plm(..., model = "within")`
  - 雙向固定效應 → `plm::plm(..., effect = "twoways")` 或 `lfe::felm(y ~ x | id + year)`
  - 多層次模型 → `lme4::lmer()` 或 `lme4::glmer()`
  - 工具變項 → `AER::ivreg()` 或 `lfe::felm(y ~ x1 | fe | x2 ~ z)`
  - 傾向分數配對 → `MatchIt::matchit()`
  - 差異中之差異 → `did::att_gt()` 或帶交互項的 `lm()`/`plm()`
  - SEM → `lavaan::sem()`
  - 存活分析 → `survival::coxph()`
- 如果論文有多個模型（如 Model 1, 2, 3），請**全部產製**
- 模型估計結束後，用 `summary()` 印出結果
- 程式碼開頭列出需要安裝的套件（`library(...)` 行）
- 每一步驟加上中文註解

請將完整 R 程式碼放在 ```r ... ``` 的 code block 中。

**若本論文是純質化研究**（如民族誌、深度訪談、論述分析、個案研究等，沒有統計模型），請直接寫：

> 本研究為質化研究，不涉及統計模型，因此無需產製 R 模擬程式碼。
> This is a qualitative study without statistical models; R simulation code is not applicable.

**不要**為質化研究強行編造模擬程式碼。

請使用條列與清楚的小標題呈現，每一部分簡潔但具體。
如果原文未明確說明某一點，請標註「未明確說明 / Not explicitly stated」，不要自行臆測。

---
論文內容：
{text}
"""

SUMMARY_PROMPT_EN = """\
Read the following academic paper and provide a rigorous, structured analysis and summary. Avoid vague descriptions; use the paper's actual concepts and terminology whenever possible.

Paper metadata:
- Title: {title}
- Authors: {authors}
- Journal: {journal}
- Volume/Issue: Vol. {volume}, No. {issue}
- Publication date: {pub_date}

Structure your output as follows:

## 1. Research Question
- What core problem does the paper try to solve?
- What is the motivation and background?

## 2. Theoretical Context / Literature Conversation
- Which literatures or theories does this research extend or respond to?
- How is it positioned (complementing, challenging, or integrating prior work)?

## 3. Theoretical Framework
- What core theories or concepts does the author use?
- How are these concepts related?

## 4. Data Source
- What data are used (survey, interviews, secondary data, experimental, etc.)?
- Sample source, size, and characteristics?

## 5. Model & Methodology
- What method (qualitative, quantitative, or mixed)?
- Specific analytical tools or models (e.g., regression, SEM, case study)?

## 6. Findings / Results
- What are the main empirical findings?
- Which hypotheses are supported / not supported?

## 7. Conclusion & Contribution
- Main conclusions?
- Contribution to theory or practice?

## 8. Limitations & Future Research
- What limitations does the author note?
- What future research directions are suggested?

Use bullet points and clear subheadings. Be concise but specific.
If the paper does not explicitly address a point, write "Not explicitly stated" — do not speculate.

---
Paper content:
{text}
"""


# ── Data class ────────────────────────────────────────────────────────────

@dataclass
class PaperSummary:
    title: str
    authors: list[str]
    doi: str
    journal: str
    volume: str
    issue: str
    publication_date: str
    research_question: str = ""          # 1. 研究問題
    theoretical_context: str = ""        # 2. 對話的理論脈絡
    theoretical_framework: str = ""      # 3. 理論架構
    data_source: str = ""                # 4. 資料來源
    model_methodology: str = ""          # 5. 研究模型與方法
    findings: str = ""                   # 6. 模型結果
    conclusion_contribution: str = ""    # 7. 重要結論與貢獻
    limitations: str = ""                # 8. 限制與未來研究
    r_simulation_code: str = ""          # 9. R 模擬重製程式碼
    raw_summary: str = ""


# ── OpenAI backend ────────────────────────────────────────────────────────

def summarize_with_openai(article: Article, paper: ExtractedPaper, lang: str = "zh") -> PaperSummary:
    """Summarize using OpenAI API (Chat Completions)."""
    try:
        from openai import OpenAI
    except ImportError:
        logger.error("openai package not installed. Run: pip install openai")
        return _empty_summary(article)

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set in .env. "
                     "Set it or use SUMMARIZER_BACKEND=local")
        return _empty_summary(article)

    text = get_relevant_text(paper, max_chars=60000)  # GPT-4o has 128k context
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

    client = OpenAI(api_key=OPENAI_API_KEY)

    logger.info(f"Sending to OpenAI ({OPENAI_MODEL}): {article.title[:60]}...")
    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[
                {"role": "system", "content":
                 "You are an expert academic research analyst. "
                 "Produce rigorous, structured summaries of academic papers."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        )
        raw_summary = response.choices[0].message.content or ""
        usage = response.usage
        if usage:
            logger.info(f"  Tokens: prompt={usage.prompt_tokens}, "
                         f"completion={usage.completion_tokens}")
    except Exception as e:
        logger.error(f"OpenAI API error: {e}")
        return _empty_summary(article)

    return _parse_summary(article, raw_summary)


# ── Claude backend ────────────────────────────────────────────────────────

def summarize_with_claude(article: Article, paper: ExtractedPaper, lang: str = "zh") -> PaperSummary:
    """Summarize using Anthropic Claude API."""
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed. Run: pip install anthropic")
        return _empty_summary(article)

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set.")
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

    logger.info(f"Sending to Claude: {article.title[:60]}...")
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

    return _parse_summary(article, raw_summary)


# ── Local (rule-based) backend ────────────────────────────────────────────

def summarize_local(article: Article, paper: ExtractedPaper) -> PaperSummary:
    """Local rule-based summarization (no API needed)."""
    summary = _empty_summary(article)
    sections = paper.sections

    abstract = sections.get("abstract", article.abstract) or ""
    intro = sections.get("introduction", "")
    theory_text = sections.get("theory", sections.get("background", ""))
    methods_text = sections.get("methods", sections.get("measures", ""))
    results_text = sections.get("results", sections.get("discussion", ""))
    conclusion = sections.get("conclusion", sections.get("discussion", ""))

    # 1. Research question
    rq = _find_sentences(abstract + "\n" + intro,
                          ["this paper", "this study", "we examine", "we investigate",
                           "we ask", "research question", "how does", "how do"])
    summary.research_question = "\n".join(rq[:5]) if rq else abstract[:500]

    # 2. Theoretical context
    context = _find_sentences(intro + "\n" + theory_text,
                               ["literature", "prior research", "existing", "builds on",
                                "drawing on", "extends", "challenges", "in contrast",
                                "consistent with"])
    summary.theoretical_context = "\n".join(context[:5])

    # 3. Theoretical framework
    if theory_text:
        summary.theoretical_framework = _truncate(theory_text, 800)
    else:
        theory_s = _find_sentences(intro,
                                    ["theory", "theoretical", "framework", "concept",
                                     "perspective", "argue that", "hypothesis"])
        summary.theoretical_framework = "\n".join(theory_s[:5])

    # 4. Data source
    data_s = _find_sentences(methods_text,
                              ["data", "dataset", "sample", "survey", "census",
                               "respondent", "observation", "N =", "n =", "cases"])
    summary.data_source = "\n".join(data_s[:5])

    # 5. Model & methodology
    method_s = _find_sentences(methods_text,
                                ["regression", "model", "method", "analysis", "estimate",
                                 "fixed effect", "logistic", "OLS", "multilevel",
                                 "qualitative", "interview", "ethnograph", "causal"])
    summary.model_methodology = "\n".join(method_s[:5])

    # 6. Findings
    finding_s = _find_sentences(results_text,
                                 ["find that", "results show", "results indicate",
                                  "evidence", "significant", "effect", "associated",
                                  "support", "consistent with", "contrary to"])
    summary.findings = "\n".join(finding_s[:5])

    # 7. Conclusion & contribution
    contrib_s = _find_sentences(conclusion,
                                 ["contribut", "implication", "advance", "extend",
                                  "conclud", "policy", "practitioner"])
    summary.conclusion_contribution = "\n".join(contrib_s[:5])

    # 8. Limitations
    lim_s = _find_sentences(conclusion + "\n" + results_text,
                             ["limitation", "caveat", "future research", "further study",
                              "should be"])
    summary.limitations = "\n".join(lim_s[:5])

    summary.raw_summary = f"[Local extraction]\n\nAbstract: {abstract}"
    return summary


# ── Helpers ───────────────────────────────────────────────────────────────

def _find_sentences(text: str, keywords: list[str]) -> list[str]:
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


def _extract_r_code(raw_text: str) -> str:
    """Extract R code blocks (```r ... ```) from the raw LLM output."""
    blocks = re.findall(r'```[rR]?\s*\n(.*?)```', raw_text, re.DOTALL)
    if blocks:
        return "\n\n".join(block.strip() for block in blocks)
    return ""


def _parse_summary(article: Article, raw_text: str) -> PaperSummary:
    """Parse LLM-generated markdown summary into structured fields."""
    summary = _empty_summary(article)
    summary.raw_summary = raw_text

    # Extract R code blocks before section parsing (they span many lines
    # and would break the line-by-line heading matcher).
    summary.r_simulation_code = _extract_r_code(raw_text)

    # Map heading keywords to fields. Order matters — more specific first.
    section_map = [
        # 9. R Simulation Code (heading only; actual code extracted above)
        (["R 模擬", "R Simulation", "R Code", "R 程式碼"], "r_simulation_code"),
        # 8. Limitations (check before "Conclusion" because that section may discuss limits)
        (["限制", "Limitations", "Future Research"], "limitations"),
        # 7. Conclusion
        (["結論", "貢獻", "Conclusion", "Contribution"], "conclusion_contribution"),
        # 6. Findings
        (["模型結果", "發現", "Findings", "Results"], "findings"),
        # 5. Model & Methodology
        (["研究模型", "研究方法", "Model", "Methodology", "Methods"], "model_methodology"),
        # 4. Data Source
        (["資料來源", "Data Source", "Data"], "data_source"),
        # 3. Theoretical Framework
        (["理論架構", "Theoretical Framework"], "theoretical_framework"),
        # 2. Theoretical Context
        (["對話的理論脈絡", "理論脈絡", "Theoretical Context", "Literature Conversation"], "theoretical_context"),
        # 1. Research Question
        (["研究問題", "Research Question"], "research_question"),
    ]

    def find_field(heading_text: str) -> str | None:
        for keywords, field in section_map:
            for kw in keywords:
                if kw in heading_text:
                    return field
        return None

    current_field = None
    current_content: list[str] = []

    for line in raw_text.split("\n"):
        stripped = line.strip()
        # Detect heading lines (start with # or ##, or a numbered pattern)
        is_heading = stripped.startswith("#") or bool(re.match(r"^\d+\.\s", stripped))

        if is_heading:
            matched_field = find_field(stripped)
            if matched_field:
                # Save previous section
                if current_field and current_field != "r_simulation_code" and current_content:
                    prev = getattr(summary, current_field, "")
                    new_content = "\n".join(current_content).strip()
                    setattr(summary, current_field,
                            (prev + "\n\n" + new_content).strip() if prev else new_content)
                # R code is already extracted via _extract_r_code();
                # don't overwrite it with raw section text.
                if matched_field == "r_simulation_code":
                    current_field = None
                    current_content = []
                else:
                    current_field = matched_field
                    current_content = []
                continue

        if current_field:
            current_content.append(line)

    # Save the last section (skip r_simulation_code — handled separately)
    if current_field and current_field != "r_simulation_code" and current_content:
        prev = getattr(summary, current_field, "")
        new_content = "\n".join(current_content).strip()
        setattr(summary, current_field,
                (prev + "\n\n" + new_content).strip() if prev else new_content)

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


# ── Dispatcher ────────────────────────────────────────────────────────────

def summarize(article: Article, paper: ExtractedPaper, lang: str = "zh",
              backend: str | None = None) -> PaperSummary:
    """Summarize a paper using the configured backend.

    Backend override takes precedence over the global SUMMARIZER_BACKEND.
    """
    b = (backend or SUMMARIZER_BACKEND or "openai").lower()
    if b == "openai":
        return summarize_with_openai(article, paper, lang=lang)
    if b == "claude":
        return summarize_with_claude(article, paper, lang=lang)
    return summarize_local(article, paper)


# ── R code regeneration (single article) ──────────────────────────────────

RCODE_PROMPT = """\
你是一位精通 R 語言和計量社會科學的研究方法專家。

以下是一篇學術論文的內容。請根據你對這篇論文的資料結構、變項定義與統計方法的理解，產出一段**完整且可直接在 R 中執行**的模擬程式碼。

論文基本資訊：
- 標題：{title}
- 作者：{authors}
- 期刊：{journal}

### 模擬數據要求：
- 涵蓋論文中提到的**所有變項**，包括：
  - 依變項（dependent variables）
  - 核心自變項（key independent variables）
  - 控制變項（control variables）：如性別、年齡、教育程度、收入、種族、地區、婚姻狀態等
  - 工具變項（instrumental variables，若有使用）
  - 固定效應識別變項（如個體 ID、時間、地區等）
  - 交互作用項（interaction terms，若有）
  - 權重變項（sampling weights，若有）
- 變項名稱與論文一致
- 樣本量 (N) 符合論文描述
- 各變項的分佈類型合理（連續、二元、計數、有序等）
- 使用 `set.seed()` 確保可重複

### 統計模型要求：
- 使用論文中**實際採用**的統計模型和 R 函數：
  - OLS → `lm()`
  - Logistic → `glm(..., family = binomial)`
  - Negative binomial → `MASS::glm.nb()`
  - 個體固定效應 → `plm::plm(..., model = "within")`
  - 雙向固定效應 → `plm::plm(..., effect = "twoways")` 或 `lfe::felm(y ~ x | id + year)`
  - 多層次模型 → `lme4::lmer()` / `lme4::glmer()`
  - 工具變項 → `AER::ivreg()` 或 `lfe::felm(y ~ x1 | fe | x2 ~ z)`
  - 傾向分數配對 → `MatchIt::matchit()`
  - DID → `did::att_gt()` 或帶交互項的 `lm()`/`plm()`
  - SEM → `lavaan::sem()`
  - 存活分析 → `survival::coxph()`
- 如果論文有多個模型（如 Model 1, 2, 3），**全部產製**
- 用 `summary()` 印出每個模型的結果
- 開頭列出所有 `library()` 指令
- 每一步加中文註解

請將完整程式碼放在 ```r ... ``` 的 code block 中。

如果這是純質化研究，請回覆：「本研究為質化研究，無需 R 模擬程式碼。」

---
論文內容：
{text}
"""


def regenerate_r_code(article: Article, paper: ExtractedPaper,
                       backend: str | None = None) -> str:
    """
    Regenerate ONLY the R simulation code for a single article.
    Uses a dedicated prompt focused entirely on code quality.
    Returns the extracted R code string.
    """
    b = (backend or SUMMARIZER_BACKEND or "openai").lower()
    text = get_relevant_text(paper, max_chars=60000 if b == "openai" else 28000)

    prompt = RCODE_PROMPT.format(
        title=article.title,
        authors=", ".join(article.authors),
        journal=article.journal,
        text=text,
    )

    raw = ""
    if b == "openai":
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info(f"Regenerating R code via OpenAI: {article.title[:60]}...")
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content":
                     "You are an expert in R programming and quantitative social science methods. "
                     "Produce complete, runnable R code with simulated data and statistical models."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=8192,
            )
            raw = response.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return ""
    elif b == "claude":
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info(f"Regenerating R code via Claude: {article.title[:60]}...")
            response = client.messages.create(
                model=ANTHROPIC_MODEL,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
        except Exception as e:
            logger.error(f"Claude error: {e}")
            return ""
    else:
        logger.warning("R code regeneration requires an API backend (openai or claude)")
        return ""

    return _extract_r_code(raw)


# ── Save / format ─────────────────────────────────────────────────────────

def save_summary(summary: PaperSummary, output_dir: Path = SUMMARY_DIR) -> Path:
    """Save summary as JSON + readable Markdown."""
    doi_suffix = summary.doi.split("/")[-1] if summary.doi else "unknown"

    json_path = output_dir / f"{doi_suffix}.json"
    json_path.write_text(
        json.dumps(asdict(summary), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_path = output_dir / f"{doi_suffix}.md"
    md_path.write_text(_format_summary_markdown(summary), encoding="utf-8")

    logger.info(f"Saved summary: {md_path.name}")
    return md_path


def _format_summary_markdown(s: PaperSummary) -> str:
    authors_str = ", ".join(s.authors) if s.authors else "N/A"
    return f"""# {s.title}

**Authors:** {authors_str}
**Journal:** {s.journal} | Vol. {s.volume}, No. {s.issue}
**DOI:** {s.doi}
**Date:** {s.publication_date}

---

## 1. 研究問題 (Research Question)

{s.research_question or "N/A"}

## 2. 對話的理論脈絡 (Theoretical Context)

{s.theoretical_context or "N/A"}

## 3. 理論架構 (Theoretical Framework)

{s.theoretical_framework or "N/A"}

## 4. 資料來源 (Data Source)

{s.data_source or "N/A"}

## 5. 研究模型與方法 (Model & Methodology)

{s.model_methodology or "N/A"}

## 6. 模型結果 (Findings / Results)

{s.findings or "N/A"}

## 7. 重要結論與貢獻 (Conclusion & Contribution)

{s.conclusion_contribution or "N/A"}

## 8. 限制與未來研究 (Limitations & Future Research)

{s.limitations or "N/A"}

## 9. R 模擬重製程式碼 (R Simulation Code)

```r
{s.r_simulation_code or "# N/A"}
```
"""
