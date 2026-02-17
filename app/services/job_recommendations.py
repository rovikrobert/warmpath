"""Recommend companies with live job openings matching the user's target role.

Scans the board registry, caches raw job listings in EnrichmentCache (6-hour TTL),
matches against the user's target role, and returns top companies sorted by
matching_count * avg_relevance.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.enrichment import EnrichmentCache
from app.services.board_registry import (
    BOARD_REGISTRY,
    companies_for_locations,
    get_display_name,
    get_region,
)
from app.services.job_fetcher import JobFetcher

logger = logging.getLogger(__name__)


async def get_cached_jobs(company_key: str, db: AsyncSession) -> list[dict] | None:
    """Read cached job listings from EnrichmentCache if not expired."""
    cache_key = f"job_scan:{company_key}"
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(EnrichmentCache).where(
            EnrichmentCache.cache_key == cache_key,
            EnrichmentCache.expires_at > now,
        )
    )
    entry = result.scalar_one_or_none()
    if entry is None:
        return None
    return entry.data.get("jobs", [])


async def set_cached_jobs(company_key: str, jobs: list[dict], db: AsyncSession) -> None:
    """Upsert cached job listings with TTL."""
    cache_key = f"job_scan:{company_key}"
    ttl = timedelta(hours=settings.RECOMMENDATION_CACHE_TTL_HOURS)
    expires_at = datetime.now(timezone.utc) + ttl

    # Serialize jobs — strip raw_data to keep cache lean
    serializable = []
    for j in jobs:
        entry = {k: v for k, v in j.items() if k != "raw_data"}
        # Convert datetime objects to ISO strings
        if "posted_at" in entry and entry["posted_at"] is not None:
            try:
                entry["posted_at"] = entry["posted_at"].isoformat()
            except AttributeError:
                pass
        serializable.append(entry)

    result = await db.execute(
        select(EnrichmentCache).where(EnrichmentCache.cache_key == cache_key)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.data = {"jobs": serializable}
        existing.expires_at = expires_at
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            EnrichmentCache(
                cache_key=cache_key,
                source="job_scan",
                data={"jobs": serializable},
                expires_at=expires_at,
            )
        )


async def _fetch_jobs(
    company_key: str,
    boards: dict[str, str],
    fetcher: JobFetcher,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Fetch jobs for one company with concurrency limit (no DB access)."""
    async with semaphore:
        try:
            return await fetcher.fetch_jobs_for_company(company_key, boards)
        except Exception:
            logger.exception("Failed to fetch jobs for %s", company_key)
            return []


async def get_recommendations(
    target_role: str,
    target_seniority: str | None,
    target_locations: list[str] | None,
    exclude_companies: list[str] | None,
    limit: int,
    db: AsyncSession,
) -> dict:
    """Return top companies with live openings matching the user's target role.

    Returns:
        {
            "recommendations": [...],
            "scan_stats": {
                "companies_scanned": int,
                "cache_hits": int,
                "fresh_scans": int,
            }
        }
    """
    fetcher = JobFetcher()
    max_scan = settings.RECOMMENDATION_MAX_SCAN
    max_results = min(limit, settings.RECOMMENDATION_MAX_RESULTS * 3)

    # Build candidate list, prioritized by location
    candidates = companies_for_locations(target_locations)

    # Apply exclusions
    exclude_set = set()
    if exclude_companies:
        for name in exclude_companies:
            exclude_set.add(name.strip().lower())
    candidates = [c for c in candidates if c not in exclude_set]

    # Phase 1: check cache for all candidates
    cached_results: dict[str, list[dict]] = {}
    uncached: list[str] = []

    for key in candidates:
        jobs = await get_cached_jobs(key, db)
        if jobs is not None:
            cached_results[key] = jobs
        else:
            uncached.append(key)

    # Phase 2: fetch uncached companies (up to max_scan, concurrency 5)
    to_fetch = uncached[:max_scan]
    cache_hits = len(cached_results)

    if to_fetch:
        semaphore = asyncio.Semaphore(5)
        tasks = []
        for key in to_fetch:
            boards = BOARD_REGISTRY.get(key, {})
            tasks.append(_fetch_jobs(key, boards, fetcher, semaphore))

        results = await asyncio.gather(*tasks)
        # Cache results sequentially (DB session is not concurrency-safe)
        for key, jobs in zip(to_fetch, results):
            cached_results[key] = jobs
            if jobs:
                await set_cached_jobs(key, jobs, db)

    await db.flush()

    # Phase 3: match jobs to role for each company
    recommendations: list[dict] = []

    for key, jobs in cached_results.items():
        if not jobs:
            continue
        matched = await fetcher.match_jobs_to_role(jobs, target_role, target_seniority)
        if not matched:
            continue

        avg_relevance = sum(j.get("role_relevance", 0) for j in matched) / len(matched)
        top_titles = [j.get("title", "") for j in matched[:3]]

        recommendations.append(
            {
                "company": key,
                "display_name": get_display_name(key),
                "region": get_region(key),
                "matching_openings": [
                    {
                        "title": j.get("title", ""),
                        "url": j.get("url", ""),
                        "location": j.get("location"),
                        "is_remote": j.get("is_remote", False),
                        "relevance": j.get("role_relevance", 0),
                    }
                    for j in matched[:5]
                ],
                "matching_count": len(matched),
                "total_openings": len(jobs),
                "top_titles": top_titles,
                "score": len(matched) * avg_relevance,
                "source": "board_registry",
            }
        )

    # Sort by score descending, then limit
    recommendations.sort(key=lambda r: r["score"], reverse=True)
    recommendations = recommendations[:max_results]

    return {
        "recommendations": recommendations,
        "scan_stats": {
            "companies_scanned": len(cached_results),
            "cache_hits": cache_hits,
            "fresh_scans": len(to_fetch),
        },
    }
