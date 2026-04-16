"""
Journal article metadata scraper.

Discovers articles from academic journals using multiple strategies:
1. CrossRef API (primary) - reliable, well-structured metadata
2. OpenAlex API (fallback) - richer data, sometimes includes PDF URLs
3. SAGE TOC page scraping (fallback) - direct publisher scraping
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import (
    CROSSREF_API_BASE,
    CROSSREF_MAILTO,
    DOWNLOAD_DELAY,
    JOURNALS,
    OPENALEX_API_BASE,
    OPENALEX_MAILTO,
    OUTPUT_DIR,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


@dataclass
class Article:
    title: str
    authors: list[str]
    doi: str
    journal: str
    volume: str = ""
    issue: str = ""
    pages: str = ""
    publication_date: str = ""
    abstract: str = ""
    pdf_url: str = ""
    landing_url: str = ""
    article_type: str = "research-article"

    @property
    def filename_safe_title(self) -> str:
        safe = re.sub(r'[^\w\s-]', '', self.title)
        safe = re.sub(r'\s+', '_', safe.strip())
        return safe[:80]

    @property
    def pdf_filename(self) -> str:
        doi_suffix = self.doi.split("/")[-1] if self.doi else "unknown"
        return f"{doi_suffix}_{self.filename_safe_title}.pdf"


def fetch_articles_crossref(issn: str, rows: int = 20) -> list[Article]:
    """Fetch recent articles from CrossRef API."""
    url = f"{CROSSREF_API_BASE}/journals/{issn}/works"
    params = {
        "rows": rows,
        "sort": "published",
        "order": "desc",
        "filter": "type:journal-article",
    }
    headers = {
        "User-Agent": f"LiteratureScraper/1.0 (mailto:{CROSSREF_MAILTO})",
    }

    logger.info(f"Fetching from CrossRef: ISSN={issn}, rows={rows}")
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"CrossRef request failed: {e}")
        return []

    data = resp.json()
    items = data.get("message", {}).get("items", [])
    articles = []

    for item in items:
        title_list = item.get("title", [])
        title = title_list[0] if title_list else "Untitled"

        authors = []
        for a in item.get("author", []):
            given = a.get("given", "")
            family = a.get("family", "")
            authors.append(f"{given} {family}".strip())

        doi = item.get("DOI", "")

        # Extract publication date
        pub_date_info = item.get("published-print") or item.get("published-online") or {}
        date_parts = pub_date_info.get("date-parts", [[]])[0]
        pub_date = "-".join(str(p) for p in date_parts) if date_parts else ""

        volume = item.get("volume", "")
        issue = item.get("issue", "")
        pages = item.get("page", "")

        abstract_raw = item.get("abstract", "")
        if abstract_raw:
            abstract = BeautifulSoup(abstract_raw, "lxml").get_text(strip=True)
        else:
            abstract = ""

        article_type = item.get("type", "journal-article")

        articles.append(Article(
            title=title,
            authors=authors,
            doi=doi,
            journal=issn,
            volume=volume,
            issue=issue,
            pages=pages,
            publication_date=pub_date,
            abstract=abstract,
            article_type=article_type,
        ))

    logger.info(f"CrossRef returned {len(articles)} articles")
    return articles


def fetch_articles_openalex(issn: str, per_page: int = 20) -> list[Article]:
    """Fetch recent articles from OpenAlex API (richer metadata, includes PDF URLs)."""
    url = f"{OPENALEX_API_BASE}/works"
    params = {
        "filter": f"primary_location.source.issn:{issn},type:article",
        "sort": "publication_date:desc",
        "per_page": per_page,
        "mailto": OPENALEX_MAILTO,
    }

    logger.info(f"Fetching from OpenAlex: ISSN={issn}")
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"OpenAlex request failed: {e}")
        return []

    data = resp.json()
    results = data.get("results", [])
    articles = []

    for work in results:
        title = work.get("title", "Untitled") or "Untitled"
        doi = (work.get("doi") or "").replace("https://doi.org/", "")

        authors = []
        for authorship in work.get("authorships", []):
            name = authorship.get("author", {}).get("display_name", "")
            if name:
                authors.append(name)

        pub_date = work.get("publication_date", "")
        biblio = work.get("biblio", {})
        volume = biblio.get("volume", "") or ""
        issue = biblio.get("issue", "") or ""
        first_page = biblio.get("first_page", "") or ""
        last_page = biblio.get("last_page", "") or ""
        pages = f"{first_page}-{last_page}" if first_page and last_page else first_page

        loc = work.get("primary_location", {}) or {}
        pdf_url = loc.get("pdf_url", "") or ""
        landing_url = loc.get("landing_page_url", "") or ""

        # OpenAlex sometimes provides abstract as inverted index
        abstract = ""
        abstract_inv = work.get("abstract_inverted_index")
        if abstract_inv:
            word_positions = []
            for word, positions in abstract_inv.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            abstract = " ".join(w for _, w in word_positions)

        articles.append(Article(
            title=title,
            authors=authors,
            doi=doi,
            journal=issn,
            volume=volume,
            issue=issue,
            pages=pages,
            publication_date=pub_date,
            abstract=abstract,
            pdf_url=pdf_url,
            landing_url=landing_url,
        ))

    logger.info(f"OpenAlex returned {len(articles)} articles")
    return articles


def scrape_sage_toc(journal_key: str) -> list[Article]:
    """Scrape SAGE table-of-contents page directly for article links."""
    journal = JOURNALS.get(journal_key)
    if not journal:
        logger.error(f"Unknown journal key: {journal_key}")
        return []

    toc_url = journal["toc_url"]
    logger.info(f"Scraping SAGE TOC: {toc_url}")

    try:
        resp = requests.get(toc_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"SAGE TOC scraping failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = []

    # SAGE uses various class patterns for article listings
    # Try multiple selectors
    article_blocks = (
        soup.select("div.issue-item") or
        soup.select("article.article") or
        soup.select("div.art_title") or
        soup.select("tr.article-row") or
        soup.select("div[class*='issue-item']")
    )

    for block in article_blocks:
        # Extract title
        title_el = (
            block.select_one("h5.issue-item__title a") or
            block.select_one("span.art_title a") or
            block.select_one("a[href*='/doi/']") or
            block.select_one("h3 a") or
            block.select_one("h4 a")
        )
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        href = title_el.get("href", "")

        # Extract DOI from href (e.g., /doi/full/10.1177/xxx or /doi/10.1177/xxx)
        doi_match = re.search(r'/doi/(?:full/|abs/)?(.+?)(?:\?|$)', href)
        doi = doi_match.group(1) if doi_match else ""

        # Extract authors
        author_els = (
            block.select("span.hlFld-ContribAuthor a") or
            block.select("span.contribDeg498 a") or
            block.select("div.issue-item__loa a")
        )
        authors = [a.get_text(strip=True) for a in author_els]

        # Build PDF URL
        pdf_url = ""
        if doi:
            pdf_url = journal["pdf_base_url"].format(doi=doi)
            landing_url = journal["landing_url"].format(doi=doi)
        else:
            landing_url = f"https://journals.sagepub.com{href}" if href.startswith("/") else href

        articles.append(Article(
            title=title,
            authors=authors,
            doi=doi,
            journal=journal["issn"],
            pdf_url=pdf_url,
            landing_url=landing_url,
        ))

    logger.info(f"SAGE TOC scraping found {len(articles)} articles")
    return articles


def fetch_latest_issue(journal_key: str, max_articles: int = 20) -> list[Article]:
    """
    Fetch the latest articles for a journal using multiple strategies.
    Returns a deduplicated, merged list of articles.
    """
    journal = JOURNALS.get(journal_key)
    if not journal:
        raise ValueError(f"Unknown journal key: {journal_key}")

    issn = journal["issn"]
    all_articles: dict[str, Article] = {}

    # Strategy 1: CrossRef
    for article in fetch_articles_crossref(issn, rows=max_articles):
        if article.doi:
            all_articles[article.doi] = article

    time.sleep(1)

    # Strategy 2: OpenAlex (may provide PDF URLs)
    for article in fetch_articles_openalex(issn, per_page=max_articles):
        if article.doi and article.doi in all_articles:
            # Merge: keep richer data
            existing = all_articles[article.doi]
            if not existing.pdf_url and article.pdf_url:
                existing.pdf_url = article.pdf_url
            if not existing.landing_url and article.landing_url:
                existing.landing_url = article.landing_url
            if not existing.abstract and article.abstract:
                existing.abstract = article.abstract
        elif article.doi:
            all_articles[article.doi] = article

    # Strategy 3: SAGE TOC scraping (fills in gaps)
    if journal.get("publisher") == "sage":
        time.sleep(1)
        for article in scrape_sage_toc(journal_key):
            if article.doi and article.doi not in all_articles:
                all_articles[article.doi] = article
            elif article.doi and article.doi in all_articles:
                existing = all_articles[article.doi]
                if not existing.pdf_url and article.pdf_url:
                    existing.pdf_url = article.pdf_url

    # Ensure all articles have PDF URLs constructed from DOI
    for article in all_articles.values():
        if not article.pdf_url and article.doi:
            article.pdf_url = journal["pdf_base_url"].format(doi=article.doi)
        if not article.landing_url and article.doi:
            article.landing_url = journal["landing_url"].format(doi=article.doi)

    articles = list(all_articles.values())

    # Filter to only research articles (skip editorials, book reviews, etc.)
    research_articles = [
        a for a in articles
        if a.article_type in ("journal-article", "research-article", "article")
        or a.article_type == ""  # SAGE TOC doesn't always set type
    ]

    logger.info(f"Total unique articles for {journal_key}: {len(research_articles)}")
    return research_articles


def save_metadata(articles: list[Article], journal_key: str) -> Path:
    """Save article metadata to JSON."""
    out_path = OUTPUT_DIR / f"{journal_key}_metadata.json"
    data = [asdict(a) for a in articles]
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    logger.info(f"Saved metadata to {out_path}")
    return out_path
