"""Job aggregator fallback — queries Adzuna API when ATS boards and career pages return nothing.

Adzuna provides a free API tier (250 calls/day) covering Singapore, India,
Australia, US, and other markets. Results are normalized to the same dict
format as job_fetcher.py output.

Docs: https://developer.adzuna.com/
"""

import contextlib
import logging
import re
from datetime import datetime

import httpx

from app.config import settings
from app.services.job_fetcher import _clean_job_title

logger = logging.getLogger(__name__)

HTTPX_TIMEOUT = 5.0

# Map WarmPath region keywords to Adzuna country codes
_LOCATION_TO_COUNTRY: dict[str, str] = {
    "singapore": "sg",
    "malaysia": "my",
    "indonesia": "id",
    "india": "in",
    "australia": "au",
    "new zealand": "nz",
    "united states": "us",
    "us": "us",
    "united kingdom": "gb",
    "uk": "gb",
    "canada": "ca",
    "germany": "de",
    "france": "fr",
}

_REMOTE_PATTERNS = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE
)


def _resolve_country(location_hint: str | None) -> str:
    """Resolve a location hint to an Adzuna country code. Defaults to 'sg'."""
    if not location_hint:
        return "sg"
    hint_lower = location_hint.strip().lower()
    for keyword, code in _LOCATION_TO_COUNTRY.items():
        if keyword in hint_lower:
            return code
    return "sg"


async def search_jobs_by_company(
    company_name: str,
    location_hint: str | None = None,
    max_results: int = 50,
) -> list[dict]:
    """Search Adzuna for jobs at a specific company.

    Returns a list of normalized job dicts compatible with job_fetcher output.
    Returns empty list if Adzuna is not configured or the request fails.
    """
    if not settings.ADZUNA_APP_ID or not settings.ADZUNA_APP_KEY:
        return []

    country = _resolve_country(location_hint)
    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": settings.ADZUNA_APP_ID,
        "app_key": settings.ADZUNA_APP_KEY,
        "what": company_name,
        "what_and": company_name,
        "results_per_page": min(max_results, 50),
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning(
            "Adzuna fetch failed for '%s' in %s: %s", company_name, country, exc
        )
        return []

    data = resp.json()
    raw_results = data.get("results", [])

    jobs: list[dict] = []
    for item in raw_results:
        title = item.get("title", "")
        if not title:
            continue

        # Filter: only include results that mention the company
        item_company = (item.get("company", {}).get("display_name", "") or "").lower()
        if (
            company_name.lower() not in item_company
            and item_company not in company_name.lower()
        ):
            continue

        location_name = item.get("location", {}).get("display_name", "") or ""

        posted_at = None
        created = item.get("created")
        if created:
            with contextlib.suppress(ValueError, TypeError):
                posted_at = datetime.fromisoformat(created.replace("Z", "+00:00"))

        jobs.append(
            {
                "title": _clean_job_title(title),
                "department": item.get("category", {}).get("label") or None,
                "location": location_name or None,
                "url": item.get("redirect_url", ""),
                "source": "adzuna",
                "source_job_id": str(item.get("id", "")),
                "posted_at": posted_at,
                "is_remote": bool(_REMOTE_PATTERNS.search(location_name)),
                "raw_data": item,
            }
        )

    logger.info(
        "Adzuna: found %d jobs for '%s' in %s (from %d raw results)",
        len(jobs),
        company_name,
        country,
        len(raw_results),
    )
    return jobs
