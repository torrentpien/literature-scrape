"""
PDF downloader for academic journals.

Downloads PDFs using institutional IP access (e.g., NCCU 140.119.x.x).
Handles SAGE-specific redirects, cookies, and Cloudflare bot protection.

SAGE uses Cloudflare which blocks Python requests. We use curl_cffi to
impersonate a real browser's TLS fingerprint and HTTP/2 settings.

IMPORTANT: When using curl_cffi, do NOT set custom headers — this breaks
the browser impersonation and Cloudflare will reject the request.
"""

import logging
import re
import time
from pathlib import Path

import requests

# Try to use curl_cffi for Cloudflare bypass
try:
    from curl_cffi import requests as cffi_requests  # type: ignore
    HAS_CURL_CFFI = True
except ImportError:
    cffi_requests = None
    HAS_CURL_CFFI = False

# Try to use playwright for JS-challenge sites (Springer Nature)
try:
    from playwright.sync_api import sync_playwright  # type: ignore
    HAS_PLAYWRIGHT = True
except ImportError:
    sync_playwright = None
    HAS_PLAYWRIGHT = False

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

# Browser profiles to try, in order (newer Chrome versions tend to work better)
IMPERSONATE_TARGETS = [
    "chrome131",
    "chrome124",
    "chrome120",
    "chrome116",
    "chrome110",
    "chrome",
    "safari17_2_ios",
    "safari15_5",
]


def _build_sage_pdf_url(doi: str) -> str:
    """Legacy helper kept for backward compat; prefer _atypon_candidates()."""
    return f"https://journals.sagepub.com/doi/pdf/{doi}"


def _pdf_candidates(article: Article) -> list[str]:
    """
    Build PDF URL candidates for an article from its metadata.

    Supports two platform types:
    - Atypon (SAGE, Chicago, T&F, Wiley): /doi/pdf/{doi}, /doi/epdf/...
    - Springer Nature: /articles/{article_id}.pdf

    Derives the host from the article's existing URLs so this works
    for any publisher automatically.
    """
    urls: list[str] = []
    if article.pdf_url:
        urls.append(article.pdf_url)

    # Derive publisher host from existing URLs
    base_host = ""
    for u in (article.pdf_url, article.landing_url):
        if u:
            m = re.match(r"(https?://[^/]+)", u)
            if m:
                base_host = m.group(1)
                break

    if not article.doi or not base_host:
        return urls

    article_id = article.doi.split("/", 1)[-1] if "/" in article.doi else article.doi

    # Detect platform type from host
    is_nature = "nature.com" in base_host

    if is_nature:
        # Springer Nature URL patterns
        patterns = [
            f"/articles/{article_id}.pdf",
            f"/articles/{article_id}",
        ]
    else:
        # Atypon URL patterns (SAGE, Chicago, T&F, Wiley)
        patterns = [
            f"/doi/pdf/{article.doi}",
            f"/doi/epdf/{article.doi}",
            f"/doi/pdfdirect/{article.doi}",
        ]

    for pattern in patterns:
        candidate = f"{base_host}{pattern}"
        if candidate not in urls:
            urls.append(candidate)

    return urls


def _cffi_get(url: str, timeout: int = REQUEST_TIMEOUT, allow_redirects: bool = True):
    """
    Make a GET request using curl_cffi with browser impersonation.

    Tries multiple browser profiles until one gets past Cloudflare.
    Does NOT set any custom headers — curl_cffi handles them internally
    to match the impersonated browser's exact header set.
    """
    for target in IMPERSONATE_TARGETS:
        try:
            resp = cffi_requests.get(
                url,
                impersonate=target,
                timeout=timeout,
                allow_redirects=allow_redirects,
            )
            # If we got past Cloudflare (not a challenge page), return
            if resp.status_code != 403 or not _is_cloudflare(resp.content):
                logger.info(f"    (impersonate={target}) HTTP {resp.status_code}")
                return resp
            logger.info(f"    (impersonate={target}) still blocked by Cloudflare")
        except Exception as e:
            logger.info(f"    (impersonate={target}) error: {e}")
            continue

    # All targets failed; return last response or raise
    logger.warning("All impersonation targets failed")
    return resp  # type: ignore


def _cffi_session_get(session, url: str, **kwargs):
    """GET using a curl_cffi session, trying multiple impersonate targets."""
    last_resp = None
    last_err = None
    for target in IMPERSONATE_TARGETS:
        try:
            resp = session.get(url, impersonate=target, **kwargs)
            last_resp = resp
            if resp.status_code != 403 or not _is_cloudflare(resp.content):
                return resp
        except Exception as e:
            last_err = e
            logger.debug(f"    ({target}) session.get error: {e}")
            continue
    if last_resp is not None:
        return last_resp
    # All attempts raised; re-raise the last one so the caller knows
    if last_err:
        raise last_err
    raise RuntimeError("All impersonation targets failed")


def _is_cloudflare(content: bytes) -> bool:
    """Check if response content is a Cloudflare challenge page."""
    text = content[:3000].decode("utf-8", errors="replace").lower()
    markers = ["just a moment", "cf-browser-verification", "cf-chl-",
               "challenge-platform", "cloudflare ray id"]
    return any(m in text for m in markers)


def _is_pdf(resp) -> bool:
    ct = resp.headers.get("Content-Type", "")
    return "pdf" in ct or resp.content[:5] == b"%PDF-"


def _describe_html(content: bytes) -> str:
    text = content[:3000].decode("utf-8", errors="replace")
    if _is_cloudflare(content):
        return "CLOUDFLARE CHALLENGE (install curl_cffi to bypass)"
    if _is_js_challenge(content):
        return "JS CHALLENGE (will try browser fallback)"
    if "Access Denied" in text or "access-denied" in text.lower():
        return "Access denied page"
    if "Sign in" in text or "Login" in text or "log in" in text.lower():
        return "Login / authentication page"
    if "captcha" in text.lower():
        return "CAPTCHA challenge"
    title_match = re.search(r'<title[^>]*>([^<]+)</title>', text, re.IGNORECASE)
    if title_match:
        return f"HTML page: '{title_match.group(1).strip()[:80]}'"
    return f"HTML page ({len(content)} bytes)"


def _is_js_challenge(content: bytes) -> bool:
    """Detect JS-based bot challenges (Springer Nature 'Client Challenge', etc.)."""
    text = content[:5000].decode("utf-8", errors="replace").lower()
    markers = ["client challenge", "challenge.js", "bot detection",
               "please enable javascript", "browser verification"]
    return any(m in text for m in markers)


def _download_with_browser(pdf_url: str, landing_url: str,
                            output_path: Path,
                            extra_pdf_urls: list[str] | None = None) -> bool:
    """
    Download a PDF using a real headless browser (Playwright).

    Used as fallback when curl_cffi fails due to JS challenges
    (e.g., Springer Nature's "Client Challenge").

    Strategy (in order):
    1. Visit landing page, solve JS challenge, grab cookies
    2. Try API request to each PDF URL candidate (uses browser cookies)
    3. Try direct page.goto() on PDF URL (follows JS redirects)
    4. Try clicking any "Download PDF" / "Get PDF" link on the landing page
       and capture the download event
    """
    if not HAS_PLAYWRIGHT:
        logger.error(
            "playwright not installed — cannot solve JS challenge. "
            "Run: pip install playwright && playwright install chromium"
        )
        return False

    logger.info("  Attempting browser-based download (playwright)...")

    all_pdf_urls = [pdf_url]
    for u in (extra_pdf_urls or []):
        if u and u not in all_pdf_urls:
            all_pdf_urls.append(u)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                accept_downloads=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()

            # ── Step 1: Solve landing-page JS challenge ────────────────
            if landing_url:
                logger.info(f"  Browser: visiting {landing_url}")
                try:
                    page.goto(landing_url, wait_until="networkidle", timeout=60000)
                except Exception as e:
                    logger.warning(f"  Landing goto failed: {e}")
                # Give it a moment for late-loading challenges
                time.sleep(3)
                cookies = context.cookies()
                logger.info(f"  Browser: got {len(cookies)} cookies after challenge")

            # ── Step 2: API request to each candidate PDF URL ──────────
            for u in all_pdf_urls:
                try:
                    logger.info(f"  Browser API: {u}")
                    resp = context.request.get(u, timeout=90000)
                    ct = resp.headers.get("content-type", "")
                    body = resp.body()
                    logger.info(f"  -> HTTP {resp.status} | {ct} | {len(body)} bytes")

                    if "pdf" in ct or body[:5] == b"%PDF-":
                        output_path.write_bytes(body)
                        size_mb = len(body) / (1024 * 1024)
                        logger.info(f"  Browser: SAVED {output_path.name} ({size_mb:.1f} MB)")
                        browser.close()
                        return True
                except Exception as e:
                    logger.info(f"  API request error: {e}")

            # ── Step 3: Page navigation to each candidate PDF URL ──────
            for u in all_pdf_urls:
                try:
                    logger.info(f"  Browser navigate: {u}")
                    # Listen for downloads triggered by navigation
                    with page.expect_download(timeout=30000) as dl_info:
                        try:
                            page.goto(u, timeout=45000)
                        except Exception:
                            pass  # navigation may throw due to download
                    try:
                        download = dl_info.value
                        download.save_as(str(output_path))
                        logger.info(f"  Browser: saved via download event: {output_path.name}")
                        browser.close()
                        return True
                    except Exception:
                        pass
                except Exception as e:
                    logger.info(f"  Page goto error: {e}")

            # ── Step 4: Click "Download PDF" link on landing page ──────
            if landing_url:
                try:
                    logger.info("  Browser: looking for Download PDF link on landing page...")
                    page.goto(landing_url, wait_until="networkidle", timeout=45000)
                    time.sleep(2)
                    # Common selectors for PDF download links
                    selectors = [
                        "a[data-track-action='download pdf']",
                        "a[data-track='Download PDF']",
                        "a:has-text('Download PDF')",
                        "a:has-text('Get PDF')",
                        "a[href$='.pdf']",
                    ]
                    link = None
                    for sel in selectors:
                        try:
                            link = page.query_selector(sel)
                            if link:
                                logger.info(f"  Found PDF link with selector: {sel}")
                                break
                        except Exception:
                            continue
                    if link:
                        with page.expect_download(timeout=60000) as dl_info:
                            link.click()
                        download = dl_info.value
                        download.save_as(str(output_path))
                        logger.info(f"  Browser: saved via click: {output_path.name}")
                        browser.close()
                        return True
                except Exception as e:
                    logger.info(f"  Click flow failed: {e}")

            browser.close()

    except Exception as e:
        logger.error(f"  Browser download failed: {type(e).__name__}: {e}")

    return False


def download_pdf(article: Article, output_dir: Path = PDF_DIR) -> Path | None:
    """
    Download a single article PDF.

    Uses curl_cffi with Chrome impersonation to bypass Cloudflare.
    Requires institutional IP access for paywalled content.
    """
    if not article.pdf_url and not article.doi:
        logger.warning(f"No PDF URL or DOI for: {article.title}")
        return None

    output_path = output_dir / article.pdf_filename

    if output_path.exists():
        logger.info(f"Already downloaded: {output_path.name}")
        return output_path

    if not HAS_CURL_CFFI and not HAS_PLAYWRIGHT:
        logger.error(
            "Neither curl_cffi nor playwright installed. "
            "Run: pip install curl_cffi playwright && playwright install chromium"
        )
        return None

    # Build list of PDF URL candidates (works for Atypon + Nature platforms)
    candidate_urls = _pdf_candidates(article)
    if not candidate_urls:
        logger.warning(f"No candidate PDF URLs for: {article.title}")
        return None

    js_challenge_detected = False

    if not HAS_CURL_CFFI:
        # Skip curl_cffi attempts, go straight to browser
        js_challenge_detected = True
    else:
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"Download attempt {attempt}/{MAX_RETRIES}: {article.title[:60]}...")

            # Use a fresh curl_cffi session per attempt (clean cookies)
            session = cffi_requests.Session()

            # Step 1: Visit landing page to warm up cookies
            if article.landing_url and attempt == 1:
                try:
                    logger.info(f"  Warming session: {article.landing_url}")
                    for target in IMPERSONATE_TARGETS:
                        try:
                            resp = session.get(
                                article.landing_url,
                                impersonate=target,
                                timeout=REQUEST_TIMEOUT,
                                allow_redirects=True,
                            )
                            cookies = dict(session.cookies) if hasattr(session.cookies, 'keys') else {}
                            logger.info(f"  Landing ({target}): HTTP {resp.status_code}, "
                                         f"cookies={list(cookies.keys())}")
                            if resp.status_code == 200:
                                break
                        except Exception as e:
                            logger.info(f"  Landing ({target}): {e}")
                            continue
                    time.sleep(1)
                except Exception as e:
                    logger.warning(f"  Landing page error: {e}")

        # Step 2: Try each PDF URL
        for url in candidate_urls:
            logger.info(f"  GET {url}")
            try:
                resp = _cffi_session_get(
                    session, url,
                    timeout=REQUEST_TIMEOUT,
                    allow_redirects=True,
                )

                ct = resp.headers.get("Content-Type", "unknown")
                logger.info(f"  -> HTTP {resp.status_code} | {ct} | {len(resp.content)} bytes"
                             f" | final URL: {resp.url}")

                if _is_pdf(resp):
                    output_path.write_bytes(resp.content)
                    size_mb = len(resp.content) / (1024 * 1024)
                    logger.info(f"  SAVED: {output_path.name} ({size_mb:.1f} MB)")
                    return output_path

                if resp.status_code == 200 and "text/html" in ct:
                    desc = _describe_html(resp.content)
                    logger.warning(f"  Got HTML instead of PDF: {desc}")
                    if "Login" in desc or "Access denied" in desc:
                        logger.error(
                            "  PAYWALL: Your IP does not have access. "
                            "Ensure you are on NCCU campus (140.119.x.x) or VPN."
                        )
                        return None
                    # Detect JS challenges (Nature "Client Challenge", etc.)
                    if _is_js_challenge(resp.content):
                        js_challenge_detected = True
                        logger.info("  JS challenge detected — will try browser fallback")
                        break  # exit URL loop → fall through to playwright
                    continue

                if resp.status_code == 403:
                    if _is_cloudflare(resp.content):
                        logger.warning(f"  Cloudflare still blocking — trying next URL/target")
                        continue
                    else:
                        logger.error(f"  HTTP 403 Forbidden — check institutional access")
                        return None

                if resp.status_code == 429:
                    wait = DOWNLOAD_DELAY * attempt * 2
                    logger.warning(f"  Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                    break

                if resp.status_code >= 400:
                    logger.warning(f"  HTTP {resp.status_code} — trying next URL")
                    continue

            except Exception as e:
                logger.warning(f"  Request error: {type(e).__name__}: {e}")
                continue

            if js_challenge_detected:
                break  # exit retry loop → fall through to playwright

            if attempt < MAX_RETRIES:
                delay = DOWNLOAD_DELAY * attempt
                logger.info(f"  Waiting {delay}s before retry...")
                time.sleep(delay)

        if not js_challenge_detected:
            logger.error(f"Failed after {MAX_RETRIES} attempts: {article.title[:60]}")
            return None

    # ── Browser fallback for JS challenges (Nature, etc.) ────────────────
    if js_challenge_detected:
        pdf_url = candidate_urls[0] if candidate_urls else ""
        extras = candidate_urls[1:] if len(candidate_urls) > 1 else []
        if _download_with_browser(pdf_url, article.landing_url, output_path,
                                    extra_pdf_urls=extras):
            return output_path
        logger.error(f"Browser fallback also failed: {article.title[:60]}")
        return None

    return None


def download_all(articles: list[Article], output_dir: Path = PDF_DIR) -> dict[str, Path]:
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
    """Diagnostic: check if current IP has institutional access to SAGE."""
    results = {"ip": "unknown", "sage_access": False, "details": "",
               "curl_cffi": HAS_CURL_CFFI}

    # Check our external IP
    for ip_url in ["https://httpbin.org/ip", "https://api.ipify.org?format=json"]:
        try:
            if HAS_CURL_CFFI:
                r = cffi_requests.get(ip_url, impersonate="chrome131", timeout=10)
            else:
                r = requests.get(ip_url, timeout=10)
            if r.ok:
                data = r.json()
                results["ip"] = data.get("origin", data.get("ip", "unknown"))
                break
        except Exception:
            continue

    if not HAS_CURL_CFFI:
        results["details"] = "curl_cffi not installed — cannot test SAGE access"
        return results

    # Test SAGE access with a known ASR article
    test_doi = "10.1177/00031224231169050"
    test_pdf = f"https://journals.sagepub.com/doi/pdf/{test_doi}"
    test_landing = f"https://journals.sagepub.com/doi/{test_doi}"

    try:
        # Try to access SAGE with browser impersonation
        for target in IMPERSONATE_TARGETS:
            try:
                logger.info(f"Testing SAGE access with impersonate={target}...")
                # Visit landing page first
                session = cffi_requests.Session()
                session.get(test_landing, impersonate=target, timeout=30)
                time.sleep(1)

                resp = session.get(test_pdf, impersonate=target,
                                   timeout=30, allow_redirects=True)
                ct = resp.headers.get("Content-Type", "")

                if _is_pdf(resp):
                    results["sage_access"] = True
                    results["details"] = (
                        f"PDF received ({len(resp.content)} bytes) "
                        f"using impersonate={target}"
                    )
                    return results

                if resp.status_code == 200 and not _is_cloudflare(resp.content):
                    # Got through Cloudflare but might be paywall HTML
                    desc = _describe_html(resp.content)
                    results["details"] = f"Cloudflare passed (target={target}), but: {desc}"
                    return results

                # Cloudflare blocked this target; try next
                logger.info(f"  {target}: HTTP {resp.status_code}, Cloudflare={_is_cloudflare(resp.content)}")

            except Exception as e:
                logger.info(f"  {target}: error: {e}")
                continue

        # All targets failed
        results["details"] = "Cloudflare blocked all impersonation targets"

    except Exception as e:
        results["details"] = f"Request failed: {e}"

    return results
