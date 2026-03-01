"""JobSpy fallback — scrapes Indeed, LinkedIn, Glassdoor, ZipRecruiter, Google Jobs.

Uses the open-source python-jobspy library to aggregate listings from major
job boards. Inserted in the fallback chain between career page scraper and
Adzuna aggregator, expanding coverage for companies without ATS boards.

Ref: https://github.com/speedyapply/JobSpy
"""

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone

from app.config import settings
from app.services.job_fetcher import (
    _clean_job_title,
    _normalize_company_name,
    company_matches,
)

logger = logging.getLogger(__name__)

_REMOTE_PATTERNS = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE
)

# Map JobSpy site_name values to our source identifiers
_SOURCE_MAP: dict[str, str] = {
    "indeed": "indeed",
    "linkedin": "linkedin_jobspy",
    "glassdoor": "glassdoor",
    "zip_recruiter": "ziprecruiter",
    "google": "google_jobs",
}

# Map location hints to Indeed country codes for JobSpy
_LOCATION_TO_INDEED_COUNTRY: dict[str, str] = {
    "singapore": "Singapore",
    "malaysia": "Malaysia",
    "indonesia": "Indonesia",
    "india": "India",
    "australia": "Australia",
    "new zealand": "New Zealand",
    "united states": "USA",
    "us": "USA",
    "united kingdom": "UK",
    "uk": "UK",
    "canada": "Canada",
    "germany": "Germany",
    "france": "France",
    "japan": "Japan",
    "hong kong": "Hong Kong",
    "philippines": "Philippines",
    "thailand": "Thailand",
    "vietnam": "Vietnam",
}


def _resolve_indeed_country(location_hint: str | None) -> str:
    """Resolve a location hint to an Indeed country code. Defaults to 'USA'."""
    if not location_hint:
        return "USA"
    hint_lower = location_hint.strip().lower()
    for keyword, code in _LOCATION_TO_INDEED_COUNTRY.items():
        if keyword in hint_lower:
            return code
    return "USA"


def _make_source_job_id(job_url: str) -> str:
    """Generate a stable source_job_id from a job URL via truncated SHA-256."""
    return hashlib.sha256(job_url.encode()).hexdigest()[:16]


def _parse_date(value: object) -> datetime | None:
    """Parse a date value from JobSpy (may be datetime, Timestamp, or string)."""
    if value is None:
        return None
    # pandas Timestamp / datetime
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    # string fallback
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    # pandas NaT or other
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    return None


def _scrape_sync(
    company_name: str,
    max_results: int = 30,
    location_hint: str | None = None,
) -> list[dict]:
    """Synchronous scraping via jobspy — runs in a thread."""
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.warning("python-jobspy not installed — skipping JobSpy fallback")
        return []

    site_names = (
        ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]
        if settings.JOBSPY_SEARCH_ALL_SITES
        else ["indeed", "linkedin"]
    )

    # Strip domain suffixes for the search query
    search_term = _normalize_company_name(company_name) or company_name

    country_indeed = _resolve_indeed_country(location_hint)

    scrape_kwargs: dict = {
        "site_name": site_names,
        "search_term": search_term,
        "results_wanted": max_results,
        "hours_old": 72,
        "country_indeed": country_indeed,
    }
    if location_hint:
        scrape_kwargs["location"] = location_hint

    try:
        df = scrape_jobs(**scrape_kwargs)
    except Exception as exc:
        logger.warning("JobSpy scrape failed for '%s': %s", company_name, exc)
        return []

    if df is None or df.empty:
        logger.info("JobSpy: no results for '%s'", company_name)
        return []

    jobs: list[dict] = []

    for _, row in df.iterrows():
        # Filter: only include results where the company field matches
        row_company = str(row.get("company", "") or "")
        if not company_matches(company_name, row_company):
            continue

        title = str(row.get("title", "") or "")
        if not title.strip():
            continue

        location = str(row.get("location", "") or "") or None
        job_url = str(row.get("job_url", "") or "")
        site_name = str(row.get("site", "") or "").lower()

        jobs.append(
            {
                "title": _clean_job_title(title),
                "department": None,
                "location": location,
                "url": job_url,
                "source": _SOURCE_MAP.get(site_name, site_name or "jobspy"),
                "source_job_id": _make_source_job_id(job_url) if job_url else "",
                "posted_at": _parse_date(row.get("date_posted")),
                "is_remote": bool(
                    row.get("is_remote")
                    or (location and _REMOTE_PATTERNS.search(location))
                ),
                "raw_data": {
                    k: (
                        v.isoformat()
                        if isinstance(v, datetime)
                        else (None if _is_na(v) else v)
                    )
                    for k, v in row.to_dict().items()
                },
            }
        )

    logger.info(
        "JobSpy: found %d jobs for '%s' (from %d raw rows)",
        len(jobs),
        company_name,
        len(df),
    )
    return jobs


def _is_na(value: object) -> bool:
    """Check if a value is pandas NA/NaT without requiring pandas import."""
    try:
        import pandas as pd

        return pd.isna(value)
    except Exception:
        return False


async def search_jobs_via_jobspy(
    company_name: str,
    max_results: int = 30,
    location_hint: str | None = None,
) -> list[dict]:
    """Async entry point — delegates to thread to avoid blocking the event loop."""
    if not settings.JOBSPY_ENABLED:
        return []

    return await asyncio.to_thread(
        _scrape_sync, company_name, max_results, location_hint
    )
