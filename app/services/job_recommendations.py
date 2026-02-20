"""Recommend companies with live job openings matching the user's target role.

Scans the board registry, caches raw job listings in EnrichmentCache (6-hour TTL),
matches against the user's target role, and returns top companies sorted by
matching_count * avg_relevance.
"""

import asyncio
import contextlib
import logging
import uuid
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
        company_key = (
            cache_key[prefix_len:] if cache_key.startswith("job_scan:") else cache_key
        )
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
            with contextlib.suppress(AttributeError):
                entry["posted_at"] = entry["posted_at"].isoformat()
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
    user_id: uuid.UUID,
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

    # Build candidate list, scoped to target locations.
    # companies_for_locations already prioritizes matched-region companies first,
    # so ATS-backed companies in the user's region are checked before others.
    # We use the full prioritized list so that regions with few ATS-compatible
    # companies (e.g. SEA with mostly career_page entries) still get results
    # from globally-hiring companies as a fallback.
    candidates = companies_for_locations(target_locations)

    # --- Network layer (primary): referral paths from WarmPath's own data ---
    from app.services.network_recommendations import get_network_recommendations

    network_recs = await get_network_recommendations(
        user_id=user_id,
        target_locations=target_locations,
        exclude_companies=exclude_companies,
        limit=limit * 2,
        db=db,
    )
    network_by_company: dict[str, dict] = {r["company_name"]: r for r in network_recs}

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
            for key, jobs in zip(to_fetch, results, strict=False):
                if jobs:
                    await set_cached_jobs(key, jobs, db)

            # Parallel: match all fetched results (no DB needed)
            match_tasks = [
                _match_and_build(fetcher, key, jobs, target_role, target_seniority)
                for key, jobs in zip(to_fetch, results, strict=False)
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

    # --- Merge network signals into ATS results + add network-only entries ---
    merged: list[dict] = []

    # Enrich ATS results with network data
    for rec in recommendations:
        net = network_by_company.pop(rec["company"], None)
        rec["network_density"] = net["network_density"] if net else 0
        rec["network_label"] = net["network_label"] if net else ""
        rec["careers_url"] = rec.get("careers_url") or (
            net["careers_url"] if net else None
        )
        merged.append(rec)

    # Add network-only companies (no ATS data)
    for _key, net in network_by_company.items():
        merged.append(
            {
                "company": net["company_name"],
                "display_name": net["display_name"],
                "region": None,
                "matching_openings": [],
                "matching_count": 0,
                "total_openings": 0,
                "top_titles": [],
                "score": 0,
                "source": "network_signal",
                "network_density": net["network_density"],
                "network_label": net["network_label"],
                "careers_url": net["careers_url"],
            }
        )

    # Re-score with network-first weighting:
    # network_density * 0.4 + job_relevance * 0.3 + ats_quality * 0.2 + recency * 0.1
    max_density = max((r["network_density"] for r in merged), default=1) or 1
    for rec in merged:
        nd = rec["network_density"] / max_density  # normalize 0-1
        jr = min(rec.get("score", 0) / 100, 1.0)  # normalize 0-1
        aq = 1.0 if rec["source"] == "ats_board" else 0.0
        rec["score"] = round(nd * 0.4 + jr * 0.3 + aq * 0.2, 3)

    merged.sort(key=lambda r: r["score"], reverse=True)
    merged = merged[:max_results]

    network_count = sum(1 for r in merged if r.get("network_density", 0) > 0)

    return {
        "recommendations": merged,
        "scan_stats": {
            "companies_scanned": cache_hits + fresh_scanned,
            "cache_hits": cache_hits,
            "fresh_scans": fresh_scanned,
            "network_matches": network_count,
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
                select(UserJobPreferences).where(UserJobPreferences.user_id == user_id)
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
            for key, jobs in zip(to_warm, results, strict=False):
                if isinstance(jobs, list) and jobs:
                    await set_cached_jobs(key, jobs, db)
                    cached_count += 1

            await db.commit()
            logger.info(
                "Warmed job cache for user %s: %d/%d companies cached",
                user_id,
                cached_count,
                len(to_warm),
            )
    except Exception:
        logger.debug("Background job cache warm failed for user %s", user_id)
