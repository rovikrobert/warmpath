"""Generic career-page scraper — fallback when Greenhouse/Lever boards are unavailable.

Fetches a company's careers page and extracts job postings from the HTML.
Uses a multi-strategy approach:
1. JSON-LD structured data (works on SPAs that embed schema.org markup)
2. Known SPA API endpoints (for high-priority companies with internal APIs)
3. Regex-based link parsing (original heuristic scraper)
"""

import contextlib
import json
import logging
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx

from app.services.job_fetcher import _clean_job_title

logger = logging.getLogger(__name__)

HTTPX_TIMEOUT = 5.0

# Known career page URLs for companies not on Greenhouse/Lever.
# Values are the base careers URL to scrape.
CAREER_PAGES: dict[str, str] = {
    # US / Global
    "google": "https://www.google.com/about/careers/applications/",
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
    "bytedance": "https://jobs.bytedance.com/en/",
    "tiktok": "https://careers.tiktok.com/",
    "wise": "https://www.wise.jobs/",
    "revolut": "https://www.revolut.com/careers/",
    "propertyguru": "https://careers.propertyguru.com/",
    "circles-life": "https://www.circles.life/sg/careers/",
    "traveloka": "https://www.traveloka.com/en-sg/careers",
    "goto": "https://www.gotocompany.com/careers",
    "binance": "https://www.binance.com/en/careers",
    "crypto-com": "https://crypto.com/careers",
    "govtech": "https://www.tech.gov.sg/careers/",
    "dbs": "https://www.dbs.com/careers/",
    "ocbc": "https://www.ocbc.com/group/careers",
    "uob": "https://www.uobgroup.com/careers/",
    "standard-chartered": "https://www.sc.com/en/careers/",
    "shopback": "https://careers.shopback.com/",
    "nium": "https://www.nium.com/careers",
    "monks-hill": "https://www.monkshill.com/careers",
    "singtel": "https://www.singtel.com/about-us/careers",
    "st-engineering": "https://www.stengg.com/careers/",
    "temasek": "https://www.temasek.com.sg/en/careers",
    "gic": "https://www.gic.com.sg/careers/",
    "capitaland": "https://www.capitaland.com/en/careers.html",
    "keppel": "https://www.keppel.com/careers",
    "singapore-airlines": "https://www.singaporeair.com/en_UK/sg/careers/",
    # India
    "razorpay": "https://razorpay.com/jobs/",
    "zerodha": "https://zerodha.com/careers/",
    "cred": "https://careers.cred.club/",
    "meesho": "https://careers.meesho.com/",
    "phonepe": "https://www.phonepe.com/careers/",
    "flipkart": "https://www.flipkartcareers.com/",
    "swiggy": "https://careers.swiggy.com/",
    # Australia / NZ
    "canva": "https://www.canva.com/careers/",
    "atlassian": "https://www.atlassian.com/company/careers",
    "afterpay": "https://www.afterpay.com/en-AU/careers",
    "xero": "https://www.xero.com/careers/",
}

# Patterns that indicate a link is a job posting
_JOB_PATH_PATTERNS = re.compile(
    r"/(jobs?|positions?|openings?|roles?|careers?/[^/]+/\d|apply)/",
    re.IGNORECASE,
)

# Patterns to extract a reasonable job title from link text or URL path
_TITLE_CLEANUP = re.compile(r"[_-]")

_REMOTE_PATTERNS = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Known SPA API endpoints — companies whose career sites are JS-rendered
# but expose public JSON APIs for job listings.
# ---------------------------------------------------------------------------

_KNOWN_SPA_APIS: dict[str, dict] = {
    "jobs.bytedance.com": {
        "url": "https://jobs.bytedance.com/api/v1/search/job/posts",
        "params": {"limit": 50},
        "parser": "_parse_bytedance_api",
    },
    "careers.tiktok.com": {
        "url": "https://careers.tiktok.com/api/v1/search/job/posts",
        "params": {"limit": 50},
        "parser": "_parse_bytedance_api",  # Same parent company, same API
    },
}


def _extract_title_from_url(url: str) -> str:
    """Best-effort title extraction from a URL path segment."""
    path = urlparse(url).path.rstrip("/")
    last_segment = path.split("/")[-1] if path else ""
    cleaned = _TITLE_CLEANUP.sub(" ", last_segment).strip()
    return cleaned.title() if cleaned else ""


def lookup_career_page(company_name: str) -> str | None:
    """Look up a known career page URL for a company.

    Strips common domain suffixes (.ai, .io, etc.) so 'cantina.ai' finds 'cantina'.
    """
    import re

    key = company_name.strip().lower()
    url = CAREER_PAGES.get(key)
    if url:
        return url
    stripped = re.sub(r"\.(ai|io|com|co|dev|app|tech|xyz|org|net)$", "", key)
    if stripped != key:
        return CAREER_PAGES.get(stripped)
    return None


async def fetch_career_page(url: str) -> list[dict]:
    """Scrape a careers page and extract job postings.

    Uses a multi-strategy approach:
    1. JSON-LD structured data (schema.org JobPosting)
    2. Known SPA API endpoints
    3. Regex-based link parsing (original heuristic)
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

    # Strategy 1: JSON-LD structured data
    jobs = _extract_jsonld_jobs(html, url)
    if jobs:
        logger.info(
            "Career page (JSON-LD): extracted %d jobs from '%s'", len(jobs), url
        )
        return jobs

    # Strategy 2: Known SPA API endpoints
    jobs = await _try_known_api(url)
    if jobs:
        logger.info(
            "Career page (SPA API): extracted %d jobs from '%s'", len(jobs), url
        )
        return jobs

    # Strategy 3: Original regex scraper
    jobs = _extract_jobs_from_html(html, url)
    logger.info("Career page (HTML): extracted %d jobs from '%s'", len(jobs), url)
    return jobs


# ---------------------------------------------------------------------------
# Strategy 1: JSON-LD extraction
# ---------------------------------------------------------------------------

_JSONLD_PATTERN = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)


def _extract_jsonld_jobs(html: str, base_url: str) -> list[dict]:
    """Extract JobPosting entries from JSON-LD structured data in HTML.

    Many career sites embed schema.org JobPosting markup for SEO, even when
    the visible page is rendered by JavaScript. This data is server-rendered
    and accessible without executing JS.
    """
    jobs: list[dict] = []

    for match in _JSONLD_PATTERN.finditer(html):
        raw = match.group(1).strip()
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            data = json.loads(raw)
            # JSON-LD can be a single object or an array
            items = data if isinstance(data, list) else [data]

            # Handle @graph containers
            expanded: list[dict] = []
            for item in items:
                if isinstance(item, dict) and "@graph" in item:
                    expanded.extend(item["@graph"])
                else:
                    expanded.append(item)

            for item in expanded:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = " ".join(item_type)
                if "JobPosting" not in item_type:
                    continue

                job = _parse_jsonld_job(item, base_url)
                if job:
                    jobs.append(job)

    return jobs


def _parse_jsonld_job(item: dict, base_url: str) -> dict | None:
    """Parse a single schema.org JobPosting into our standard format."""
    title = item.get("title", "") or item.get("name", "")
    if not title:
        return None

    # Location
    location_name = ""
    job_location = item.get("jobLocation")
    if isinstance(job_location, dict):
        address = job_location.get("address", {})
        if isinstance(address, dict):
            parts = [
                address.get("addressLocality", ""),
                address.get("addressRegion", ""),
                address.get("addressCountry", ""),
            ]
            location_name = ", ".join(p for p in parts if p)
        elif isinstance(address, str):
            location_name = address
    elif isinstance(job_location, str):
        location_name = job_location

    # Department / category
    department = None
    occ_cat = item.get("occupationalCategory")
    if isinstance(occ_cat, str):
        department = occ_cat
    industry = item.get("industry")
    if not department and isinstance(industry, str):
        department = industry

    # URL
    job_url = item.get("url", "") or base_url
    if not job_url.startswith("http"):
        job_url = urljoin(base_url, job_url)

    # Date
    posted_at = None
    date_str = item.get("datePosted")
    if date_str:
        with contextlib.suppress(ValueError, TypeError):
            posted_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

    # Remote detection
    job_loc_type = item.get("jobLocationType", "")
    is_remote = (
        isinstance(job_loc_type, str) and "remote" in job_loc_type.lower()
    ) or bool(location_name and _REMOTE_PATTERNS.search(location_name))

    return {
        "title": _clean_job_title(title),
        "department": department,
        "location": location_name or None,
        "url": job_url,
        "source": "career_page_jsonld",
        "source_job_id": item.get("identifier", {}).get("value", job_url)
        if isinstance(item.get("identifier"), dict)
        else job_url,
        "posted_at": posted_at,
        "is_remote": is_remote,
        "raw_data": {"scraped_from": base_url, "method": "jsonld"},
    }


# ---------------------------------------------------------------------------
# Strategy 2: Known SPA API endpoints
# ---------------------------------------------------------------------------


async def _try_known_api(url: str) -> list[dict]:
    """Try known SPA API endpoints for the career page's domain."""
    domain = urlparse(url).netloc.lower()
    api_config = _KNOWN_SPA_APIS.get(domain)
    if not api_config:
        return []

    try:
        async with httpx.AsyncClient(
            timeout=HTTPX_TIMEOUT,
            headers={"Accept": "application/json"},
        ) as client:
            resp = await client.get(api_config["url"], params=api_config.get("params"))
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.debug("SPA API fetch failed for '%s': %s", domain, exc)
        return []

    parser_name = api_config.get("parser", "")
    if parser_name == "_parse_bytedance_api":
        return _parse_bytedance_api(resp.json(), url)

    return []


def _parse_bytedance_api(data: dict, base_url: str) -> list[dict]:
    """Parse ByteDance/TikTok job search API response."""
    jobs: list[dict] = []
    posts = data.get("data", {}).get("job_post_list", [])

    for post in posts:
        title = post.get("title", "")
        if not title:
            continue

        location_name = ""
        city_list = post.get("city_info", [])
        if city_list and isinstance(city_list, list):
            city_names = [
                c.get("city_name", "") for c in city_list if isinstance(c, dict)
            ]
            location_name = ", ".join(n for n in city_names if n)

        job_id = post.get("id", "")
        job_url = (
            f"https://jobs.bytedance.com/en/position/{job_id}/detail"
            if job_id
            else base_url
        )

        jobs.append(
            {
                "title": _clean_job_title(title),
                "department": post.get("job_category", {}).get("name") or None,
                "location": location_name or None,
                "url": job_url,
                "source": "career_page_api",
                "source_job_id": str(job_id) if job_id else job_url,
                "posted_at": None,
                "is_remote": bool(_REMOTE_PATTERNS.search(location_name))
                if location_name
                else False,
                "raw_data": {"scraped_from": base_url, "method": "spa_api"},
            }
        )

    return jobs


# ---------------------------------------------------------------------------
# Strategy 3: Original regex-based link parsing
# ---------------------------------------------------------------------------


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
                "title": _clean_job_title(title),
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
