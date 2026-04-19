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


def fetch_articles_rss(journal_key: str) -> list[Article]:
    """
    Fetch articles from the journal's RSS feed.

    RSS is the most reliable source for SAGE because:
    - Designed for automated consumption (less aggressive blocking)
    - Well-structured XML format
    - Updated when new issues are published
    - Bypasses Cloudflare challenges that affect TOC scraping

    Tries multiple candidate RSS URLs (configured in JOURNALS[key]['rss_urls']
    or 'rss_url') and returns articles from the first successful feed.
    """
    journal = JOURNALS.get(journal_key)
    if not journal:
        logger.error(f"Unknown journal key: {journal_key}")
        return []

    # Accept both single URL (legacy) and list of URLs
    urls: list[str] = []
    if journal.get("rss_urls"):
        urls = list(journal["rss_urls"])
    elif journal.get("rss_url"):
        urls = [journal["rss_url"]]

    if not urls:
        logger.info(f"No RSS URL configured for {journal_key}")
        return []

    # Browser-like User-Agent (some SAGE endpoints reject bot UA on RSS)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5",
        "Accept-Language": "en-US,en;q=0.9",
    }

    # Try to use curl_cffi for RSS too — Nature's RSS feed is also
    # behind Cloudflare and will 403 with plain requests.
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        _has_cffi = True
    except ImportError:
        cffi_requests = None
        _has_cffi = False

    cffi_targets = ["chrome131", "chrome120", "chrome"]

    resp = None
    rss_url = None
    for candidate in urls:
        logger.info(f"Trying RSS: {candidate}")

        # Attempt 1: curl_cffi with browser impersonation (bypasses Cloudflare)
        if _has_cffi:
            for target in cffi_targets:
                try:
                    r = cffi_requests.get(candidate, impersonate=target,
                                          timeout=REQUEST_TIMEOUT, allow_redirects=True)
                    logger.info(f"  ({target}) HTTP {r.status_code}, "
                                f"Content-Type={r.headers.get('Content-Type','?')}, "
                                f"{len(r.content)} bytes")
                    if r.ok and r.content:
                        first_bytes = r.content.lstrip()[:200].decode("utf-8", errors="replace")
                        if first_bytes.startswith("<?xml") or first_bytes.lstrip().startswith("<"):
                            resp = r
                            rss_url = candidate
                            break
                        else:
                            logger.warning(f"  Not XML. First 100 chars: {first_bytes[:100]!r}")
                    else:
                        logger.info(f"  ({target}) HTTP {r.status_code}")
                except Exception as e:
                    logger.info(f"  ({target}) error: {e}")
            if resp:
                break

        # Attempt 2: plain requests (works for non-Cloudflare sites)
        if not resp:
            try:
                r = requests.get(candidate, headers=headers, timeout=REQUEST_TIMEOUT)
                logger.info(f"  (requests) HTTP {r.status_code}, "
                            f"Content-Type={r.headers.get('Content-Type','?')}, "
                            f"{len(r.content)} bytes")
                if r.ok and r.content:
                    first_bytes = r.content.lstrip()[:200].decode("utf-8", errors="replace")
                    if first_bytes.startswith("<?xml") or first_bytes.lstrip().startswith("<"):
                        resp = r
                        rss_url = candidate
                        break
                    else:
                        logger.warning(f"  Not XML. First 100 chars: {first_bytes[:100]!r}")
                else:
                    logger.warning(f"  HTTP {r.status_code} — trying next URL")
            except requests.RequestException as e:
                logger.warning(f"  Request failed: {e}")

    if resp is None:
        logger.error(f"All RSS URLs failed for {journal_key}")
        return []

    logger.info(f"Using RSS URL: {rss_url}")

    # Parse RSS XML using lxml
    from lxml import etree
    try:
        # RSS feeds may declare encoding in XML prolog; pass bytes
        root = etree.fromstring(resp.content)
    except Exception as e:
        logger.error(f"RSS parse failed: {e}")
        logger.debug(f"First 500 chars of response: {resp.content[:500]!r}")
        return []

    # Collect namespace map (RSS uses dc:, content:, prism:, etc.)
    nsmap = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "content": "http://purl.org/rss/1.0/modules/content/",
        "prism": "http://prismstandard.org/namespaces/basic/2.0/",
        "atom": "http://www.w3.org/2005/Atom",
    }

    # Handle RSS 2.0 (<item>), RSS 1.0 / RDF (also <item> but in rdf namespace),
    # and Atom (<entry>). findall with local-name wildcard covers RDF-namespaced items.
    items = root.findall(".//item")
    if not items:
        # RSS 1.0 / RDF uses a namespaced <item>; match by local-name
        items = root.findall(".//{http://purl.org/rss/1.0/}item")
    if not items:
        items = root.findall(".//atom:entry", nsmap)
    if not items:
        # Last resort: any element named "item" regardless of namespace
        items = [el for el in root.iter() if etree.QName(el).localname == "item"]

    logger.info(f"Parsed {len(items)} <item>/<entry> elements from RSS")

    articles = []
    for item in items:
        title = _xml_text(item, "title") or _xml_text(item, "atom:title", nsmap) or "Untitled"
        link = _xml_text(item, "link") or ""
        if not link:
            # Atom uses <link href="..."/>
            link_el = item.find("atom:link", nsmap)
            if link_el is not None:
                link = link_el.get("href", "")

        # DOI extraction from various fields
        doi = (
            _xml_text(item, "prism:doi", nsmap) or
            _xml_text(item, "dc:identifier", nsmap) or
            ""
        )
        # Sometimes DOI is embedded in the link URL
        if not doi and link:
            m = re.search(r'(?:doi/(?:abs/|full/|pdf/)?|doi\.org/)(10\.\d+/[^?\s&#]+)', link)
            if m:
                doi = m.group(1)

        # Clean "doi:" prefix if present
        doi = re.sub(r'^doi:\s*', '', doi).strip()

        # Authors: RSS often uses <dc:creator> (can repeat)
        authors: list[str] = []
        for creator in item.findall("dc:creator", nsmap):
            if creator.text:
                # Some feeds cram all authors in one creator tag separated by ";" or ","
                names = re.split(r'[,;]\s+|\s+and\s+', creator.text.strip())
                authors.extend(n.strip() for n in names if n.strip())
        # Also try <author>
        if not authors:
            for au in item.findall("author"):
                if au.text:
                    authors.append(au.text.strip())
        # Atom <atom:author><atom:name>
        if not authors:
            for au in item.findall("atom:author/atom:name", nsmap):
                if au.text:
                    authors.append(au.text.strip())

        # Description / abstract
        description = (
            _xml_text(item, "description") or
            _xml_text(item, "content:encoded", nsmap) or
            _xml_text(item, "atom:summary", nsmap) or
            ""
        )
        # Strip HTML if present
        if description and ("<" in description):
            description = BeautifulSoup(description, "lxml").get_text(" ", strip=True)

        # Publication date
        pub_date = (
            _xml_text(item, "pubDate") or
            _xml_text(item, "dc:date", nsmap) or
            _xml_text(item, "prism:publicationDate", nsmap) or
            _xml_text(item, "atom:published", nsmap) or
            ""
        )
        # Normalize common RSS date formats to YYYY-MM-DD
        pub_date = _normalize_date(pub_date)

        # Volume / issue (PRISM namespace, if present)
        volume = _xml_text(item, "prism:volume", nsmap) or ""
        issue = _xml_text(item, "prism:number", nsmap) or ""

        # Build URLs.
        # Nature uses {article_id} in templates (e.g., "s41558-025-02345-7"),
        # Atypon publishers use {doi}. We extract the article_id from the DOI
        # (the part after the prefix like "10.1038/") and provide both placeholders.
        pdf_url = ""
        landing_url = link
        if doi:
            article_id = doi.split("/", 1)[-1] if "/" in doi else doi
            try:
                pdf_url = journal["pdf_base_url"].format(doi=doi, article_id=article_id)
            except KeyError:
                pdf_url = journal["pdf_base_url"].format(doi=doi)
            try:
                landing_url = journal["landing_url"].format(doi=doi, article_id=article_id)
            except KeyError:
                landing_url = journal["landing_url"].format(doi=doi)

        articles.append(Article(
            title=title.strip(),
            authors=authors,
            doi=doi,
            journal=journal["issn"],
            volume=volume,
            issue=issue,
            publication_date=pub_date,
            abstract=description,
            pdf_url=pdf_url,
            landing_url=landing_url,
        ))

    logger.info(f"RSS returned {len(articles)} articles")
    return articles


def _xml_text(element, path: str, nsmap: dict | None = None) -> str:
    """
    Safely extract ALL text from an XML element by XPath-like path,
    including text inside nested children.

    This matters for RSS titles like:
      <title>Book Review: <i>The Book</i> by Author</title>
    where el.text would only return "Book Review: " (before <i>).
    Using itertext() we get the full "Book Review: The Book by Author".
    """
    try:
        el = element.find(path, nsmap) if nsmap else element.find(path)
        if el is None:
            return ""
        # Collect text from the element and all its descendants in order
        parts = list(el.itertext())
        text = "".join(parts).strip()
        # Collapse whitespace (newlines inside nested tags become spaces)
        text = re.sub(r'\s+', ' ', text)
        return text
    except Exception:
        pass
    return ""


def _normalize_date(date_str: str) -> str:
    """Normalize various date formats to YYYY-MM-DD."""
    if not date_str:
        return ""
    # Already ISO format
    if re.match(r'^\d{4}-\d{2}-\d{2}', date_str):
        return date_str[:10]
    # RFC 822: "Mon, 15 May 2023 00:00:00 GMT"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return date_str


def scrape_atypon_toc(journal_key: str) -> list[Article]:
    """
    Scrape an Atypon-platform TOC page (SAGE, Chicago, T&F all use Atypon).

    Uses curl_cffi if available to bypass Cloudflare. Falls back to
    plain requests otherwise (will likely fail on SAGE).
    """
    journal = JOURNALS.get(journal_key)
    if not journal:
        logger.error(f"Unknown journal key: {journal_key}")
        return []

    toc_url = journal.get("toc_url")
    if not toc_url:
        return []

    logger.info(f"Scraping TOC: {toc_url}")

    # Prefer curl_cffi (Atypon platforms typically sit behind Cloudflare)
    try:
        from curl_cffi import requests as cffi_requests  # type: ignore
        resp = cffi_requests.get(toc_url, impersonate="chrome131",
                                 timeout=REQUEST_TIMEOUT, allow_redirects=True)
    except ImportError:
        try:
            resp = requests.get(toc_url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"TOC scraping failed: {e}")
            return []
    except Exception as e:
        logger.error(f"TOC scraping failed: {e}")
        return []

    if resp.status_code != 200:
        logger.error(f"TOC returned HTTP {resp.status_code}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    articles = []

    # Atypon uses these class patterns across SAGE, Chicago, T&F, Wiley
    article_blocks = (
        soup.select("div.issue-item") or
        soup.select("article.article") or
        soup.select("div.art_title") or
        soup.select("tr.article-row") or
        soup.select("div[class*='issue-item']") or
        soup.select("li.toc-item")
    )

    # Derive base host from toc_url (so same code works for SAGE + uchicago)
    host_match = re.match(r"(https?://[^/]+)", toc_url)
    base_host = host_match.group(1) if host_match else ""

    for block in article_blocks:
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

        # Extract DOI from href: /doi/full/10.xxx, /doi/abs/10.xxx, /doi/10.xxx
        doi_match = re.search(r'/doi/(?:full/|abs/|pdf/)?(10\.\d+/[^?\s&#]+)', href)
        doi = doi_match.group(1) if doi_match else ""

        author_els = (
            block.select("span.hlFld-ContribAuthor a") or
            block.select("span.contribDeg498 a") or
            block.select("div.issue-item__loa a") or
            block.select("a.author")
        )
        authors = [a.get_text(strip=True) for a in author_els]

        pdf_url = ""
        landing_url = ""
        if doi:
            pdf_url = journal["pdf_base_url"].format(doi=doi)
            landing_url = journal["landing_url"].format(doi=doi)
        elif href.startswith("/") and base_host:
            landing_url = base_host + href
        else:
            landing_url = href

        articles.append(Article(
            title=title,
            authors=authors,
            doi=doi,
            journal=journal["issn"],
            pdf_url=pdf_url,
            landing_url=landing_url,
        ))

    logger.info(f"TOC scraping found {len(articles)} articles")
    return articles


# Backward-compat alias
scrape_sage_toc = scrape_atypon_toc


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

    PLACEHOLDER_TITLES = {"", "Untitled", "[No title]", "N/A"}

    def _merge(article: Article):
        """Add or merge an article into the dict (preserves richer data)."""
        if not article.doi:
            return
        if article.doi not in all_articles:
            all_articles[article.doi] = article
            return
        existing = all_articles[article.doi]
        # Fill in gaps from the new article
        for field_name in ("pdf_url", "landing_url", "abstract",
                           "volume", "issue", "pages", "publication_date"):
            if not getattr(existing, field_name) and getattr(article, field_name):
                setattr(existing, field_name, getattr(article, field_name))
        # Title: replace if existing is empty or a placeholder like "Untitled",
        # but incoming has a real title. Otherwise prefer the LONGER title
        # (RSS titles are sometimes truncated).
        if article.title and article.title not in PLACEHOLDER_TITLES:
            if existing.title in PLACEHOLDER_TITLES:
                existing.title = article.title
            elif len(article.title) > len(existing.title) + 10:
                existing.title = article.title
        # Merge authors if existing has none
        if not existing.authors and article.authors:
            existing.authors = article.authors

    # Strategy 1: RSS (highest priority for publishers that provide it)
    # RSS is the most reliable and up-to-date source for new issues.
    if journal.get("rss_urls") or journal.get("rss_url"):
        for article in fetch_articles_rss(journal_key):
            _merge(article)
        time.sleep(1)

    # Strategy 2: CrossRef (authoritative bibliographic metadata)
    for article in fetch_articles_crossref(issn, rows=max_articles):
        _merge(article)
    time.sleep(1)

    # Strategy 3: OpenAlex (richer metadata, may provide OA PDF URLs)
    for article in fetch_articles_openalex(issn, per_page=max_articles):
        _merge(article)

    # Strategy 4: TOC scraping (last resort for Atypon-based publishers).
    # Works for SAGE, University of Chicago Press, Taylor & Francis, Wiley.
    if journal.get("publisher") in ("sage", "uchicago", "tandf", "wiley") and len(all_articles) < 3:
        time.sleep(1)
        logger.info("Few articles found; trying TOC scraping as fallback")
        for article in scrape_atypon_toc(journal_key):
            _merge(article)

    # Ensure all articles have PDF/landing URLs constructed from DOI.
    # Nature uses {article_id} (suffix after DOI prefix); Atypon uses {doi}.
    for article in all_articles.values():
        if article.doi:
            article_id = article.doi.split("/", 1)[-1] if "/" in article.doi else article.doi
            if not article.pdf_url:
                try:
                    article.pdf_url = journal["pdf_base_url"].format(
                        doi=article.doi, article_id=article_id)
                except KeyError:
                    article.pdf_url = journal["pdf_base_url"].format(doi=article.doi)
            if not article.landing_url:
                try:
                    article.landing_url = journal["landing_url"].format(
                        doi=article.doi, article_id=article_id)
                except KeyError:
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
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved metadata to {out_path}")
    return out_path
