"""
PDF downloader for academic journals.

Downloads PDFs using institutional IP access (e.g., NCCU 140.119.x.x).
Handles SAGE-specific redirects, cookies, and Cloudflare bot protection.

SAGE uses Cloudflare's JavaScript challenge which blocks plain `requests`
even from campus IPs with institutional access. We use `curl_cffi` to
impersonate Chrome's TLS fingerprint, which passes Cloudflare's check.
"""

import logging
import time
from pathlib import Path

import requests

# Try to use curl_cffi for Cloudflare bypass; fall back to requests
try:
    from curl_cffi import requests as cffi_requests  # type: ignore
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CURL_CFFI = False

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

# Browser profile to impersonate for Cloudflare-protected sites
BROWSER_IMPERSONATE = "chrome120"


def _build_sage_pdf_url(doi: str) -> str:
    """Build SAGE PDF URL from DOI."""
    return f"https://journals.sagepub.com/doi/pdf/{doi}"


def _create_session():
    """
    Create a session that bypasses Cloudflare bot detection.

    Returns a curl_cffi session (impersonating Chrome) if available,
    otherwise falls back to a regular requests.Session — which will
    likely fail on Cloudflare-protected sites like SAGE.
    """
    if HAS_CURL_CFFI:
        logger.debug("Using curl_cffi (Chrome impersonation) for Cloudflare bypass")
        session = cffi_requests.Session(impersonate=BROWSER_IMPERSONATE)
        session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
        })
        return session

    logger.warning(
        "curl_cffi not installed — Cloudflare-protected sites (SAGE) will fail. "
        "Install it with: pip install curl_cffi"
    )
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    session.headers.update({
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-TW;q=0.8",
    })
    return session


def _warm_session(session, landing_url: str) -> None:
    """
    Visit the article landing page first to:
    1. Pick up session cookies
    2. Establish a referrer chain that SAGE expects
    3. Pass any Cloudflare checks
    """
    if not landing_url:
        return
    try:
        logger.info(f"  Warming session: {landing_url}")
        resp = session.get(landing_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        logger.info(f"  Landing page: HTTP {resp.status_code}, "
                     f"cookies={list(session.cookies.keys())}")
    except requests.RequestException as e:
        logger.warning(f"  Landing page failed: {e}")


def _is_pdf(resp: requests.Response) -> bool:
    """Check if a response actually contains a PDF."""
    ct = resp.headers.get("Content-Type", "")
    return "pdf" in ct or resp.content[:5] == b"%PDF-"


def _describe_html(content: bytes) -> str:
    """Extract a short description from an HTML response for diagnostics."""
    text = content[:3000].decode("utf-8", errors="replace")

    # Cloudflare challenge pages (most common SAGE issue)
    cf_markers = [
        "Just a moment",
        "cf-browser-verification",
        "cf-chl-",
        "cloudflare",
        "challenge-platform",
        "Cloudflare Ray ID",
    ]
    if any(m.lower() in text.lower() for m in cf_markers):
        return "CLOUDFLARE CHALLENGE (install curl_cffi to bypass)"

    if "Access Denied" in text or "access-denied" in text.lower():
        return "Access denied page"
    if "Sign in" in text or "Login" in text or "log in" in text.lower():
        return "Login / authentication page"
    if "captcha" in text.lower():
        return "CAPTCHA challenge"

    import re
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
    if title_match:
        return f"HTML page: '{title_match.group(1).strip()[:80]}'"
    return f"HTML page ({len(content)} bytes)"


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

    # Candidate PDF URLs to try (primary, then alternatives)
    candidate_urls = [pdf_url]
    if article.doi:
        direct = _build_sage_pdf_url(article.doi)
        if direct != pdf_url:
            candidate_urls.append(direct)
        # Some SAGE PDFs need /doi/epdf/ instead of /doi/pdf/
        epdf = f"https://journals.sagepub.com/doi/epdf/{article.doi}"
        candidate_urls.append(epdf)

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"Download attempt {attempt}/{MAX_RETRIES}: {article.title[:60]}...")

        # Warm session on first attempt (get cookies from landing page)
        if attempt == 1:
            _warm_session(session, article.landing_url)
            time.sleep(1)

        for url in candidate_urls:
            try:
                logger.info(f"  GET {url}")

                # Set Referer to the landing page (SAGE checks this)
                if article.landing_url:
                    session.headers["Referer"] = article.landing_url

                resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)

                ct = resp.headers.get("Content-Type", "unknown")
                logger.info(f"  -> HTTP {resp.status_code} | {ct} | {len(resp.content)} bytes"
                             f" | final URL: {resp.url}")

                # Success: got a PDF
                if _is_pdf(resp):
                    output_path.write_bytes(resp.content)
                    size_mb = len(resp.content) / (1024 * 1024)
                    logger.info(f"  SAVED: {output_path.name} ({size_mb:.1f} MB)")
                    return output_path

                # Got HTML instead of PDF
                if resp.status_code == 200 and "text/html" in ct:
                    desc = _describe_html(resp.content)
                    logger.warning(f"  Got HTML instead of PDF: {desc}")
                    # Don't try more URLs for auth/paywall issues
                    if "Login" in desc or "Access denied" in desc:
                        logger.error(
                            f"  PAYWALL: Your IP does not have access. "
                            f"Ensure you are on institutional network (NCCU 140.119.x.x) or VPN."
                        )
                        return None
                    continue  # try next candidate URL

                # HTTP error — 403 from Cloudflare means the bypass failed,
                # not necessarily that the IP lacks access.
                if resp.status_code == 403:
                    desc = _describe_html(resp.content) if resp.content else ""
                    if "CLOUDFLARE" in desc:
                        logger.error(f"  HTTP 403 — Cloudflare blocked the request")
                        if not HAS_CURL_CFFI:
                            logger.error(f"  Install curl_cffi: pip install curl_cffi")
                    else:
                        logger.error(f"  HTTP 403 Forbidden — check institutional access")
                    return None

                if resp.status_code == 429:
                    wait = DOWNLOAD_DELAY * attempt * 2
                    logger.warning(f"  Rate limited (429). Waiting {wait}s...")
                    time.sleep(wait)
                    break  # retry outer loop

                if resp.status_code >= 400:
                    logger.warning(f"  HTTP {resp.status_code} — trying next URL")
                    continue

            except Exception as e:
                # curl_cffi raises its own exception hierarchy; catch broadly.
                logger.warning(f"  Request error: {type(e).__name__}: {e}")
                continue

        # Delay before next attempt
        if attempt < MAX_RETRIES:
            delay = DOWNLOAD_DELAY * attempt
            logger.info(f"  Waiting {delay}s before retry...")
            time.sleep(delay)

    logger.error(f"Failed after {MAX_RETRIES} attempts: {article.title[:60]}")
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

        if i < total:
            time.sleep(DOWNLOAD_DELAY)

    logger.info(f"Downloaded {len(downloaded)}/{total} PDFs")
    return downloaded


def check_access() -> dict:
    """
    Diagnostic: check if the current IP has institutional access to SAGE.
    Returns a dict with IP info and access test results.
    """
    results = {"ip": "unknown", "sage_access": False, "details": "",
               "curl_cffi": HAS_CURL_CFFI}

    # Check our external IP
    try:
        r = requests.get("https://httpbin.org/ip", timeout=10)
        if r.ok:
            results["ip"] = r.json().get("origin", "unknown")
    except Exception:
        try:
            r = requests.get("https://api.ipify.org?format=json", timeout=10)
            if r.ok:
                results["ip"] = r.json().get("ip", "unknown")
        except Exception:
            pass

    # Test SAGE access with a known ASR article
    test_doi = "10.1177/00031224231169050"
    test_url = f"https://journals.sagepub.com/doi/pdf/{test_doi}"
    session = _create_session()

    try:
        # Warm session
        session.get(f"https://journals.sagepub.com/doi/{test_doi}", timeout=30)
        time.sleep(1)

        resp = session.get(test_url, timeout=30, allow_redirects=True)
        ct = resp.headers.get("Content-Type", "")

        if _is_pdf(resp):
            results["sage_access"] = True
            results["details"] = f"PDF received ({len(resp.content)} bytes)"
        elif "text/html" in ct:
            results["details"] = _describe_html(resp.content)
        else:
            results["details"] = f"HTTP {resp.status_code}, Content-Type: {ct}"
    except Exception as e:
        results["details"] = f"Request failed: {e}"

    return results
