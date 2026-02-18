"""Recommend companies with live job openings matching the user's target role.

Scans the board registry, caches raw job listings in EnrichmentCache (6-hour TTL),
matches against the user's target role, and returns top companies sorted by
matching_count * avg_relevance.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.utils.performance import timed

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


def _job_cache_key(company_key: str) -> str:
    return f"job_scan:{company_key}"


async def get_cached_jobs(company_key: str, db: AsyncSession) -> list[dict] | None:
    """Read cached job listings from EnrichmentCache if not expired."""
    cache_key = _job_cache_key(company_key)
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


async def get_cached_jobs_batch(
    company_keys: list[str], db: AsyncSession
) -> dict[str, list[dict]]:
    """Batch-read cached job listings for multiple companies (one query)."""
    if not company_keys:
        return {}
    now = datetime.now(timezone.utc)
    cache_keys = [_job_cache_key(k) for k in company_keys]
    result = await db.execute(
        select(EnrichmentCache.cache_key, EnrichmentCache.data).where(
            EnrichmentCache.cache_key.in_(cache_keys),
            EnrichmentCache.expires_at > now,
        )
    )
    key_to_jobs: dict[str, list[dict]] = {}
    prefix_len = len("job_scan:")
    for row in result.all():
        cache_key, data = row[0], row[1]
        company_key = cache_key[prefix_len:] if cache_key.startswith("job_scan:") else cache_key
        jobs = (data or {}).get("jobs", [])
        key_to_jobs[company_key] = jobs
    return key_to_jobs


async def set_cached_jobs(company_key: str, jobs: list[dict], db: AsyncSession) -> None:
    """Upsert cached job listings with TTL."""
    cache_key = _job_cache_key(company_key)
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


_FETCH_TIMEOUT = 5.0  # Total seconds for all fresh fetches combined


async def _match_and_build(
    fetcher: JobFetcher,
    key: str,
    jobs: list[dict],
    target_role: str,
    target_seniority: str | None,
) -> dict | None:
    """Match jobs for one company and build a recommendation entry."""
    if not jobs:
        return None
    matched = await fetcher.match_jobs_to_role(jobs, target_role, target_seniority)
    if not matched:
        return None

    avg_relevance = sum(j.get("role_relevance", 0) for j in matched) / len(matched)
    top_titles = [j.get("title", "") for j in matched[:3]]

    return {
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


@timed("job_recommendations")
async def get_recommendations(
    target_role: str,
    target_seniority: str | None,
    target_locations: list[str] | None,
    exclude_companies: list[str] | None,
    limit: int,
    db: AsyncSession,
) -> dict:
    """Return top companies with live openings matching the user's target role.

    Performance strategy (cache-first):
      1. Return cached results immediately — no external HTTP if cache has enough.
      2. Only fetch fresh data if cached results < limit, with a 5s total timeout.
      3. Location-scoped scanning: skip non-matching regions when location is set.

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
    max_results = min(limit, settings.RECOMMENDATION_MAX_RESULTS * 3)

    # Build candidate list, scoped to target locations
    all_candidates = companies_for_locations(target_locations)

    # When locations specified, only scan the prioritized (matched-region) companies.
    # companies_for_locations returns matched first, then rest. We limit to the
    # matched portion to avoid scanning irrelevant regions.
    if target_locations:
        from app.services.board_registry import _LOCATION_TO_REGIONS, REGIONS

        matched_regions: set[str] = set()
        for loc in target_locations:
            loc_lower = loc.strip().lower()
            for keyword, regions in _LOCATION_TO_REGIONS.items():
                if keyword in loc_lower or loc_lower in keyword:
                    matched_regions.update(regions)

        if matched_regions:
            region_keys: set[str] = set()
            for region in matched_regions:
                region_keys.update(REGIONS.get(region, []))
            candidates = [c for c in all_candidates if c in region_keys]
        else:
            candidates = all_candidates
    else:
        candidates = all_candidates

    # Apply exclusions
    exclude_set = set()
    if exclude_companies:
        for name in exclude_companies:
            exclude_set.add(name.strip().lower())
    candidates = [c for c in candidates if c not in exclude_set]

    # Phase 1: Batch-check cache for all candidates (one query)
    cached_results = await get_cached_jobs_batch(candidates, db)
    uncached = [k for k in candidates if k not in cached_results]

    cache_hits = len(cached_results)

    # Phase 2: Match cached results in parallel (no DB access needed)
    match_tasks = [
        _match_and_build(fetcher, key, jobs, target_role, target_seniority)
        for key, jobs in cached_results.items()
    ]
    match_results = await asyncio.gather(*match_tasks)
    recommendations = [r for r in match_results if r is not None]

    # Phase 3: Only fetch fresh data if we don't have enough results.
    # Use a tight timeout so we never block longer than _FETCH_TIMEOUT.
    fresh_scanned = 0
    max_scan = settings.RECOMMENDATION_MAX_SCAN

    if len(recommendations) < max_results and uncached:
        to_fetch = uncached[:max_scan]

        async def _fetch_and_match_batch() -> list[dict]:
            """Fetch + match uncached companies within timeout."""
            batch_recs: list[dict] = []
            semaphore = asyncio.Semaphore(5)
            tasks = []
            for key in to_fetch:
                boards = BOARD_REGISTRY.get(key, {})
                tasks.append(_fetch_jobs(key, boards, fetcher, semaphore))

            results = await asyncio.gather(*tasks)

            # Sequential: write to cache (needs DB session)
            for key, jobs in zip(to_fetch, results):
                if jobs:
                    await set_cached_jobs(key, jobs, db)

            # Parallel: match all fetched results (no DB needed)
            match_tasks = [
                _match_and_build(fetcher, key, jobs, target_role, target_seniority)
                for key, jobs in zip(to_fetch, results)
                if jobs
            ]
            batch_recs = [r for r in await asyncio.gather(*match_tasks) if r]
            return batch_recs

        try:
            fresh_recs = await asyncio.wait_for(
                _fetch_and_match_batch(), timeout=_FETCH_TIMEOUT
            )
            recommendations.extend(fresh_recs)
            fresh_scanned = len(to_fetch)
        except asyncio.TimeoutError:
            logger.warning(
                "Recommendation fresh fetch timed out after %.1fs (tried %d companies)",
                _FETCH_TIMEOUT,
                len(to_fetch),
            )
            fresh_scanned = len(to_fetch)

        await db.flush()

    # Sort by score descending, then limit
    recommendations.sort(key=lambda r: r["score"], reverse=True)
    recommendations = recommendations[:max_results]

    return {
        "recommendations": recommendations,
        "scan_stats": {
            "companies_scanned": cache_hits + fresh_scanned,
            "cache_hits": cache_hits,
            "fresh_scans": fresh_scanned,
        },
    }


async def warm_job_cache_for_user(user_id: str) -> None:
    """Pre-fetch and cache job listings for a user's target locations.

    Called as a background task on login so the recommendations endpoint
    can serve from cache instantly when the user visits Find Referrals.
    """
    from app.database import _get_session_factory
    from app.models.job import UserJobPreferences

    try:
        async with _get_session_factory()() as db:
            result = await db.execute(
                select(UserJobPreferences).where(
                    UserJobPreferences.user_id == user_id
                )
            )
            prefs = result.scalar_one_or_none()
            if not prefs or not prefs.target_role:
                return

            locations = prefs.target_locations if prefs.target_locations else None
            candidates = companies_for_locations(locations)

            # Only warm uncached companies (single batch query)
            cached = await get_cached_jobs_batch(candidates, db)
            to_warm = [k for k in candidates if k not in cached]

            if not to_warm:
                logger.debug("Job cache already warm for user %s", user_id)
                return

            # Limit to avoid excessive fetching
            to_warm = to_warm[: settings.RECOMMENDATION_MAX_SCAN]

            fetcher = JobFetcher()
            semaphore = asyncio.Semaphore(5)
            tasks = [
                _fetch_jobs(key, BOARD_REGISTRY.get(key, {}), fetcher, semaphore)
                for key in to_warm
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)
            cached_count = 0
            for key, jobs in zip(to_warm, results):
                if isinstance(jobs, list) and jobs:
                    await set_cached_jobs(key, jobs, db)
                    cached_count += 1

            await db.commit()
            logger.info(
                "Warmed job cache for user %s: %d/%d companies cached",
                user_id, cached_count, len(to_warm),
            )
    except Exception:
        logger.debug("Background job cache warm failed for user %s", user_id)
