"""
Journal PDF Scraper - Configuration

Define journals, API settings, output paths, and scheduling options.
"""

import os
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent

# Auto-load .env file if present (so API keys in .env work without explicit
# `export` or a separate dotenv library)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        _key = _key.strip()
        _val = _val.strip().strip("'\"")
        # Don't override existing environment variables
        if _key and _key not in os.environ:
            os.environ[_key] = _val
OUTPUT_DIR = BASE_DIR / "output"
PDF_DIR = OUTPUT_DIR / "pdfs"
SUMMARY_DIR = OUTPUT_DIR / "summaries"
LOG_DIR = BASE_DIR / "logs"

for d in [PDF_DIR, SUMMARY_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Journal registry ──────────────────────────────────────────────────────
# Each journal entry defines how to discover and download articles.
# - issn: used for CrossRef / OpenAlex queries
# - publisher: determines PDF URL construction
# - pdf_base_url: template for building PDF download links from DOI
JOURNALS = {
    "asr": {
        "name": "American Sociological Review",
        "issn": "0003-1224",
        "publisher": "sage",
        "pdf_base_url": "https://journals.sagepub.com/doi/pdf/{doi}",
        "landing_url": "https://journals.sagepub.com/doi/{doi}",
        "toc_url": "https://journals.sagepub.com/toc/asra/current",
        # SAGE provides several RSS feed URLs; we try them in order.
        # The correct format uses underscores (rss_2_0) not rss2_0.
        "rss_urls": [
            "https://journals.sagepub.com/action/showFeed?jc=asra&type=etoc&feed=rss_2_0",
            "https://journals.sagepub.com/action/showFeed?jc=asra&type=etoc&feed=rss_1_0",
            "https://journals.sagepub.com/action/showFeed?ui=0&mi=ehikzz&ai=2b4&jc=asra&type=etoc&feed=rss_2_0",
        ],
    },
    "ajs": {
        "name": "American Journal of Sociology",
        "issn": "0002-9602",
        "publisher": "uchicago",
        "pdf_base_url": "https://www.journals.uchicago.edu/doi/pdf/{doi}",
        "landing_url": "https://www.journals.uchicago.edu/doi/{doi}",
        "toc_url": "https://www.journals.uchicago.edu/toc/ajs/current",
        "rss_urls": [
            "https://www.journals.uchicago.edu/action/showFeed?jc=ajs&type=etoc&feed=rss_2_0",
            "https://www.journals.uchicago.edu/action/showFeed?jc=ajs&type=etoc&feed=rss_1_0",
        ],
    },
    "nclimate": {
        "name": "Nature Climate Change",
        "issn": "1758-678X",
        "publisher": "nature",
        "pdf_base_url": "https://www.nature.com/articles/{article_id}.pdf",
        "landing_url": "https://www.nature.com/articles/{article_id}",
        "toc_url": "https://www.nature.com/nclimate/articles?type=article",
        "rss_urls": [
            "https://www.nature.com/nclimate.rss",
        ],
    },
    "jcc": {
        "name": "Journal of Contemporary China",
        "issn": "1067-0564",
        "publisher": "tandf",
        # Taylor & Francis uses Atypon — same URL patterns as SAGE/Chicago.
        "pdf_base_url": "https://www.tandfonline.com/doi/pdf/{doi}",
        "landing_url": "https://www.tandfonline.com/doi/{doi}",
        "toc_url": "https://www.tandfonline.com/toc/cjcc20/current",
        "rss_urls": [
            "https://www.tandfonline.com/action/showFeed?jc=cjcc20&type=etoc&feed=rss_2_0",
            "https://www.tandfonline.com/action/showFeed?jc=cjcc20&type=etoc&feed=rss_1_0",
        ],
    },
    "chinaq": {
        "name": "The China Quarterly",
        "issn": "0305-7410",
        "publisher": "cambridge",
        # Cambridge Core has complex PDF URLs; we rely on doi.org redirect
        # for landing and playwright "Download PDF" click for the actual PDF.
        "pdf_base_url": "https://www.cambridge.org/core/services/aop-cambridge-core/content/view/{article_id}",
        "landing_url": "https://doi.org/{doi}",
        "toc_url": "https://www.cambridge.org/core/journals/china-quarterly/latest-issue",
        "rss_urls": [],
    },
    "socprob": {
        "name": "Social Problems",
        "issn": "0037-7791",
        "publisher": "oup",
        # OUP Silverchair: PDF URLs are complex (include vol/issue/page).
        # We use doi.org landing + playwright click for PDF.
        "pdf_base_url": "https://academic.oup.com/socpro/article-pdf/doi/{doi}",
        "landing_url": "https://doi.org/{doi}",
        "toc_url": "https://academic.oup.com/socpro/issue",
        "rss_urls": [
            "https://academic.oup.com/socpro/rss",
        ],
    },
    "socforces": {
        "name": "Social Forces",
        "issn": "0037-7732",
        "publisher": "oup",
        "pdf_base_url": "https://academic.oup.com/sf/article-pdf/doi/{doi}",
        "landing_url": "https://doi.org/{doi}",
        "toc_url": "https://academic.oup.com/sf/issue",
        "rss_urls": [
            "https://academic.oup.com/sf/rss",
        ],
    },
}

# ── API settings ──────────────────────────────────────────────────────────
# CrossRef (primary metadata source)
CROSSREF_API_BASE = "https://api.crossref.org"
CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "your-email@example.com")

# OpenAlex (fallback / richer metadata)
OPENALEX_API_BASE = "https://api.openalex.org"
OPENALEX_MAILTO = os.getenv("OPENALEX_MAILTO", CROSSREF_MAILTO)

# ── Download settings ─────────────────────────────────────────────────────
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Seconds between consecutive PDF downloads (be polite to publisher servers)
DOWNLOAD_DELAY = 3

# Maximum retries for failed downloads
MAX_RETRIES = 3

# Request timeout in seconds
REQUEST_TIMEOUT = 60

# ── Summarization settings ────────────────────────────────────────────────
# Choose summarization backend:
# - "openai" (default): OpenAI GPT; requires OPENAI_API_KEY
# - "claude": Anthropic Claude; requires ANTHROPIC_API_KEY
# - "local":  rule-based extraction (no API key needed, lower quality)
SUMMARIZER_BACKEND = os.getenv("SUMMARIZER_BACKEND", "openai")

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# ── Scheduler settings ────────────────────────────────────────────────────
# Cron-like schedule: how often to check for new issues
# Format for schedule library: "monday", "day", "hour", etc.
SCHEDULE_INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "168"))  # weekly
