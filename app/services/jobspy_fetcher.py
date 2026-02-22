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
from app.services.job_fetcher import _clean_job_title

logger = logging.getLogger(__name__)

_REMOTE_PATTERNS = re.compile(
    r"\b(remote|anywhere|distributed|work from home|wfh)\b", re.IGNORECASE
)

# Domain suffixes to strip from company names before searching
_DOMAIN_SUFFIXES = re.compile(
    r"\.(ai|io|com|co|dev|app|tech|xyz|org|net)$", re.IGNORECASE
)

# Map JobSpy site_name values to our source identifiers
_SOURCE_MAP: dict[str, str] = {
    "indeed": "indeed",
    "linkedin": "linkedin_jobspy",
    "glassdoor": "glassdoor",
    "zip_recruiter": "ziprecruiter",
    "google": "google_jobs",
}


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


def _normalize_company_name(name: str) -> str:
    """Strip domain suffixes and normalize for search/matching.

    'Cantina.ai' → 'cantina', 'Stripe' → 'stripe'
    """
    clean = name.strip().lower()
    clean = _DOMAIN_SUFFIXES.sub("", clean)
    return clean


def _company_matches(query: str, candidate: str) -> bool:
    """Check if the candidate company name matches the query.

    Requires the query to appear at the START of the candidate name so
    'cantina' matches 'Cantina AI' and 'Cantina, Inc.' but NOT
    'Muertos Cantina' or 'On the Border Mexican Grill and Cantina'.
    """
    query_norm = _normalize_company_name(query)
    candidate_norm = _normalize_company_name(candidate)

    if not query_norm or not candidate_norm:
        return False

    # Exact match
    if query_norm == candidate_norm:
        return True

    # Query must appear at the start of candidate name
    # e.g. 'cantina' matches 'cantina ai', 'cantina, inc.' but not 'muertos cantina'
    if candidate_norm.startswith(query_norm):
        return True

    # Candidate starts with query (handles 'stripe' matching 'stripe payments')
    return query_norm.startswith(candidate_norm)


def _scrape_sync(company_name: str, max_results: int = 30) -> list[dict]:
    """Synchronous scraping via jobspy — runs in a thread."""
    try:
        from jobspy import scrape_jobs
    except ImportError:
        logger.warning("python-jobspy not installed — skipping JobSpy fallback")
        return []

    site_names = (
        ["indeed", "linkedin", "glassdoor", "zip_recruiter", "google"]
        if settings.JOBSPY_SEARCH_ALL_SITES
        else ["indeed"]
    )

    # Strip domain suffixes for the search query
    search_term = _normalize_company_name(company_name) or company_name

    try:
        df = scrape_jobs(
            site_name=site_names,
            search_term=search_term,
            results_wanted=max_results,
            hours_old=72,
            country_indeed="USA",
        )
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
        if not _company_matches(company_name, row_company):
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
    company_name: str, max_results: int = 30
) -> list[dict]:
    """Async entry point — delegates to thread to avoid blocking the event loop."""
    if not settings.JOBSPY_ENABLED:
        return []

    return await asyncio.to_thread(_scrape_sync, company_name, max_results)
