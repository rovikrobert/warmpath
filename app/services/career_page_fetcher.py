"""Generic career-page scraper — fallback when Greenhouse/Lever boards are unavailable.

Fetches a company's careers page and extracts job postings from the HTML.
Uses simple heuristics (anchor tags with job-like paths) rather than heavy
DOM parsing to keep dependencies minimal.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

HTTPX_TIMEOUT = 3.0

# Known career page URLs for companies not on Greenhouse/Lever.
# Values are the base careers URL to scrape.
CAREER_PAGES: dict[str, str] = {
    # US / Global
    "google": "https://www.google.com/about/careers/applications/jobs/results",
    "openai": "https://openai.com/careers/",
    "shopify": "https://www.shopify.com/careers/search",
    # Singapore / SEA
    "grab": "https://grab.careers/jobs/",
    "sea-group": "https://www.sea.com/careers",
    "shopee": "https://careers.shopee.sg/jobs",
    "lazada": "https://www.lazada.com/en/careers/",
    "gojek": "https://www.gojek.com/en-id/careers/",
    "carousell": "https://about.carousell.com/careers/",
    "foodpanda": "https://careers.foodpanda.com/",
    "ninja-van": "https://www.ninjavan.co/en-sg/careers",
    "patsnap": "https://www.patsnap.com/careers",
    "endowus": "https://endowus.com/careers",
    "syfe": "https://www.syfe.com/careers",
    "aspire": "https://aspireapp.com/careers",
    "funding-societies": "https://fundingsocieties.com/careers",
    "carro": "https://www.carro.co/careers",
    # India
    "razorpay": "https://razorpay.com/jobs/",
    "zerodha": "https://zerodha.com/careers/",
    "cred": "https://careers.cred.club/",
    "meesho": "https://careers.meesho.com/",
    "phonepe": "https://www.phonepe.com/careers/",
    # Australia / NZ
    "canva": "https://www.canva.com/careers/",
    "atlassian": "https://www.atlassian.com/company/careers",
    "afterpay": "https://www.afterpay.com/en-AU/careers",
}

# Patterns that indicate a link is a job posting
_JOB_PATH_PATTERNS = re.compile(
    r"/(jobs?|positions?|openings?|roles?|careers?/[^/]+/\d|apply)/",
    re.IGNORECASE,
)

# Patterns to extract a reasonable job title from link text or URL path
_TITLE_CLEANUP = re.compile(r"[_-]")


def _extract_title_from_url(url: str) -> str:
    """Best-effort title extraction from a URL path segment."""
    path = urlparse(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    cleaned = _TITLE_CLEANUP.sub(" ", last_segment).strip()
    return cleaned.title() if cleaned else ""


def lookup_career_page(company_name: str) -> str | None:
    """Look up a known career page URL for a company."""
    key = company_name.strip().lower()
    return CAREER_PAGES.get(key)


async def fetch_career_page(url: str) -> list[dict]:
    """Scrape a careers page and extract job-like links.

    Returns a list of normalized job dicts compatible with the job_fetcher
    output format. This is a best-effort heuristic scraper — it won't catch
    every job on every page, but provides useful coverage for companies
    without ATS board APIs.
    """
    try:
        async with httpx.AsyncClient(
            timeout=HTTPX_TIMEOUT,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; WarmPath/1.0; +https://warmpath.com)",
                "Accept": "text/html",
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("Career page fetch failed for '%s': %s", url, exc)
        return []

    html = resp.text
    jobs = _extract_jobs_from_html(html, url)
    logger.info("Career page: extracted %d jobs from '%s'", len(jobs), url)
    return jobs


def _extract_jobs_from_html(html: str, base_url: str) -> list[dict]:
    """Extract job postings from raw HTML using regex-based link parsing."""
    # Find all anchor tags
    anchor_pattern = re.compile(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    seen_urls: set[str] = set()
    jobs: list[dict] = []

    for match in anchor_pattern.finditer(html):
        href = match.group(1).strip()
        link_text = re.sub(r"<[^>]+>", "", match.group(2)).strip()

        # Resolve relative URLs
        full_url = urljoin(base_url, href)

        # Skip non-http, anchors, and already-seen
        if not full_url.startswith("http"):
            continue
        if full_url in seen_urls:
            continue

        # Check if this looks like a job posting link
        if not _JOB_PATH_PATTERNS.search(full_url):
            continue

        seen_urls.add(full_url)

        # Use link text as title, fall back to URL extraction
        title = link_text if len(link_text) > 3 else _extract_title_from_url(full_url)
        if not title:
            continue

        # Skip navigation links (very short or generic)
        if title.lower() in {"apply", "apply now", "view", "see all", "more"}:
            continue

        jobs.append(
            {
                "title": title,
                "department": None,
                "location": None,
                "url": full_url,
                "source": "career_page",
                "source_job_id": full_url,
                "posted_at": None,
                "is_remote": False,
                "raw_data": {"scraped_from": base_url},
            }
        )

    return jobs
