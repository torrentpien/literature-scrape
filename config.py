"""
Journal PDF Scraper - Configuration

Define journals, API settings, output paths, and scheduling options.
"""

import os
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
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
        "rss_url": "https://journals.sagepub.com/action/showFeed?jc=asra&type=etoc&feed=rss2_0",
    },
    # Add more journals here, e.g.:
    # "ajs": {
    #     "name": "American Journal of Sociology",
    #     "issn": "0002-9602",
    #     "publisher": "chicago",
    #     "pdf_base_url": "https://www.journals.uchicago.edu/doi/pdf/{doi}",
    #     "landing_url": "https://www.journals.uchicago.edu/doi/{doi}",
    #     "toc_url": "https://www.journals.uchicago.edu/toc/ajs/current",
    #     "rss_url": "https://www.journals.uchicago.edu/action/showFeed?jc=ajs&type=etoc&feed=rss",
    # },
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
# Choose summarization backend: "claude" or "local"
# - "claude": uses Anthropic Claude API (requires ANTHROPIC_API_KEY env var)
# - "local": rule-based extraction (no API key needed, lower quality)
SUMMARIZER_BACKEND = os.getenv("SUMMARIZER_BACKEND", "claude")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")

# ── Scheduler settings ────────────────────────────────────────────────────
# Cron-like schedule: how often to check for new issues
# Format for schedule library: "monday", "day", "hour", etc.
SCHEDULE_INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "168"))  # weekly
