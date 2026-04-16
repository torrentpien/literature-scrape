"""
PDF downloader for academic journals.

Downloads PDFs using institutional IP access (e.g., NCCU 140.119.x.x).
Handles SAGE-specific redirects, cookies, and access control.
"""

import logging
import time
from pathlib import Path

import requests

from config import (
    DOWNLOAD_DELAY,
    JOURNALS,
    MAX_RETRIES,
    PDF_DIR,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT,
)
from src.scraper import Article

logger = logging.getLogger(__name__)


def _build_sage_pdf_url(doi: str) -> str:
    """Build SAGE PDF URL from DOI."""
    return f"https://journals.sagepub.com/doi/pdf/{doi}"


def _create_session() -> requests.Session:
    """Create a requests session with appropriate headers for SAGE."""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    # SAGE sometimes requires accepting cookies first
    session.headers.update({
        "Accept": "application/pdf,application/xhtml+xml,text/html,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
        "Referer": "https://journals.sagepub.com/",
    })
    return session


def download_pdf(article: Article, output_dir: Path = PDF_DIR) -> Path | None:
    """
    Download a single article PDF.

    Requires institutional IP access for paywalled content.
    Returns the path to the downloaded file, or None if download failed.
    """
    if not article.pdf_url and not article.doi:
        logger.warning(f"No PDF URL or DOI for: {article.title}")
        return None

    pdf_url = article.pdf_url or _build_sage_pdf_url(article.doi)
    output_path = output_dir / article.pdf_filename

    if output_path.exists():
        logger.info(f"Already downloaded: {output_path.name}")
        return output_path

    session = _create_session()

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"Downloading (attempt {attempt}): {article.title[:60]}...")
            logger.debug(f"  URL: {pdf_url}")

            # First visit the landing page to pick up session cookies
            if article.landing_url:
                session.get(article.landing_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                time.sleep(1)

            # Download the PDF
            resp = session.get(pdf_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
            resp.raise_for_status()

            content_type = resp.headers.get("Content-Type", "")

            # Check if we actually got a PDF
            if "pdf" in content_type or resp.content[:5] == b"%PDF-":
                output_path.write_bytes(resp.content)
                file_size_mb = len(resp.content) / (1024 * 1024)
                logger.info(f"  Saved: {output_path.name} ({file_size_mb:.1f} MB)")
                return output_path

            # If we got HTML instead of PDF, likely a login/paywall page
            if "text/html" in content_type:
                logger.warning(f"  Got HTML instead of PDF. "
                             f"Possible paywall - check institutional access.")
                # Try the direct SAGE PDF URL pattern with /doi/pdf/
                if "/doi/pdf/" not in pdf_url:
                    alt_url = _build_sage_pdf_url(article.doi)
                    logger.info(f"  Trying alternate URL: {alt_url}")
                    resp2 = session.get(alt_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
                    if resp2.content[:5] == b"%PDF-":
                        output_path.write_bytes(resp2.content)
                        logger.info(f"  Saved via alternate URL: {output_path.name}")
                        return output_path

                logger.error(f"  Cannot access PDF (paywall). "
                           f"Ensure you are on institutional network (e.g., NCCU 140.119.x.x)")
                return None

            logger.warning(f"  Unexpected content type: {content_type}")

        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout on attempt {attempt}")
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response else "?"
            logger.warning(f"  HTTP {status} on attempt {attempt}")
            if status == 403:
                logger.error("  Access denied. Check institutional IP access.")
                return None
            if status == 429:
                wait = DOWNLOAD_DELAY * attempt * 2
                logger.info(f"  Rate limited. Waiting {wait}s...")
                time.sleep(wait)
        except requests.exceptions.RequestException as e:
            logger.warning(f"  Request error on attempt {attempt}: {e}")

        if attempt < MAX_RETRIES:
            time.sleep(DOWNLOAD_DELAY * attempt)

    logger.error(f"Failed to download after {MAX_RETRIES} attempts: {article.title[:60]}")
    return None


def download_all(articles: list[Article], output_dir: Path = PDF_DIR) -> dict[str, Path]:
    """
    Download PDFs for all articles.

    Returns a dict mapping DOI -> downloaded file path.
    """
    downloaded = {}
    total = len(articles)

    for i, article in enumerate(articles, 1):
        logger.info(f"[{i}/{total}] Processing: {article.title[:60]}...")
        path = download_pdf(article, output_dir)
        if path:
            downloaded[article.doi] = path

        # Polite delay between downloads
        if i < total:
            time.sleep(DOWNLOAD_DELAY)

    logger.info(f"Downloaded {len(downloaded)}/{total} PDFs")
    return downloaded
