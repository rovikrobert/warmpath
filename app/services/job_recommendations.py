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
    _resolve_regions,
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
    location_hint: str | None = None,
) -> list[dict]:
    """Fetch jobs for one company with concurrency limit (no DB access)."""
    async with semaphore:
        try:
            return await fetcher.fetch_jobs_for_company(
                company_key, boards, location_hint=location_hint
            )
        except Exception:
            logger.exception("Failed to fetch jobs for %s", company_key)
            return []


_FETCH_TIMEOUT = 5.0  # Total seconds for all fresh fetches combined


async def _fetch_fresh_and_match(
    to_fetch: list[str],
    fetcher: JobFetcher,
    target_role: str,
    target_seniority: str | None,
    location_hint: str | None,
    db: AsyncSession,
    target_locations: list[str] | None = None,
) -> tuple[list[dict], int]:
    """Fetch uncached companies within timeout, cache results, return matches.

    Uses asyncio.wait so that companies completing before the deadline are
    captured even when others are still in-flight.

    Returns (matched_recommendations, completed_count).
    """
    semaphore = asyncio.Semaphore(5)

    # Create named tasks so we can map results back to companies
    fetch_tasks: dict[asyncio.Task, str] = {}
    for key in to_fetch:
        boards = BOARD_REGISTRY.get(key, {})
        task = asyncio.create_task(
            _fetch_jobs(key, boards, fetcher, semaphore, location_hint=location_hint)
        )
        fetch_tasks[task] = key

    # Wait up to _FETCH_TIMEOUT — collect whatever completes in time
    done, pending = await asyncio.wait(fetch_tasks.keys(), timeout=_FETCH_TIMEOUT)

    # Cancel stragglers
    for task in pending:
        task.cancel()

    if pending:
        logger.warning(
            "Recommendation fresh fetch: %d/%d completed in %.1fs",
            len(done),
            len(fetch_tasks),
            _FETCH_TIMEOUT,
        )

    # Collect results from completed tasks
    fetched: dict[str, list[dict]] = {}
    for task in done:
        key = fetch_tasks[task]
        try:
            jobs = task.result()
            if jobs:
                fetched[key] = jobs
        except Exception:
            logger.exception("Failed to get result for %s", key)

    # Cache completed results (each in its own savepoint)
    for key, jobs in fetched.items():
        try:
            async with db.begin_nested():
                await set_cached_jobs(key, jobs, db)
        except Exception:
            logger.exception("Failed to cache jobs for %s", key)

    # Match fetched results in parallel
    match_tasks_list = [
        _match_and_build(
            fetcher, key, jobs, target_role, target_seniority, target_locations
        )
        for key, jobs in fetched.items()
    ]
    recs: list[dict] = []
    if match_tasks_list:
        match_results = await asyncio.gather(*match_tasks_list)
        recs = [r for r in match_results if r]

    return recs, len(done)


async def _match_and_build(
    fetcher: JobFetcher,
    key: str,
    jobs: list[dict],
    target_role: str,
    target_seniority: str | None,
    target_locations: list[str] | None = None,
) -> dict | None:
    """Match jobs for one company and build a recommendation entry."""
    if not jobs:
        return None
    matched = await fetcher.match_jobs_to_role(
        jobs, target_role, target_seniority, company_name=key
    )
    if not matched:
        return None

    # Re-rank so in-region jobs appear first in matching_openings
    if target_locations:
        loc_terms = [loc.strip().lower() for loc in target_locations if loc.strip()]
        ranked = sorted(
            matched,
            key=lambda j: (
                not (
                    any(t in (j.get("location") or "").lower() for t in loc_terms)
                    or j.get("is_remote", False)
                ),
                -j.get("role_relevance", 0),
            ),
        )
    else:
        ranked = matched

    avg_relevance = sum(j.get("role_relevance", 0) for j in ranked) / len(ranked)
    top_titles = [j.get("title", "") for j in ranked[:3]]

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
            for j in ranked[:5]
        ],
        "matching_count": len(ranked),
        "total_openings": len(jobs),
        "top_titles": top_titles,
        "score": len(ranked) * avg_relevance,
        "source": "board_registry",
    }


async def _get_user_target_companies(user_id: uuid.UUID, db: AsyncSession) -> set[str]:
    """Collect target companies from the user's SearchRequests."""
    import json

    from app.models.search_request import SearchRequest

    result = await db.execute(
        select(SearchRequest.target_companies).where(
            SearchRequest.user_id == user_id,
            SearchRequest.deleted_at.is_(None),
            SearchRequest.target_companies.isnot(None),
        )
    )
    targets: set[str] = set()
    for (companies,) in result.all():
        if not companies:
            continue
        if isinstance(companies, str):
            companies = json.loads(companies)
        targets.update(c.strip().lower() for c in companies)
    return targets


@timed("job_recommendations")
async def get_recommendations(
    user_id: uuid.UUID,
    target_role: str,
    target_seniority: str | None,
    target_locations: list[str] | None,
    exclude_companies: list[str] | None,
    limit: int,
    db: AsyncSession,
    target_industries: list[str] | None = None,
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

    # Append user's target companies so the full fallback chain runs for them
    user_targets = await _get_user_target_companies(user_id, db)
    candidate_set = set(candidates)
    candidates.extend(t for t in user_targets if t not in candidate_set)

    # --- Network layer (primary): referral paths from WarmPath's own data ---
    from app.services.network_recommendations import get_network_recommendations

    network_recs = await get_network_recommendations(
        user_id=user_id,
        target_locations=target_locations,
        exclude_companies=exclude_companies,
        target_industries=target_industries,
        limit=limit * 2,
        db=db,
    )
    network_by_company: dict[str, dict] = {r["company_name"]: r for r in network_recs}

    # Apply exclusions
    exclude_set = {n.strip().lower() for n in (exclude_companies or [])}
    candidates = [c for c in candidates if c not in exclude_set]

    # Phase 1: Batch-check cache for all candidates (one query)
    cached_results = await get_cached_jobs_batch(candidates, db)
    uncached = [k for k in candidates if k not in cached_results]

    cache_hits = len(cached_results)

    # Phase 2: Match cached results in parallel (no DB access needed)
    match_tasks = [
        _match_and_build(
            fetcher, key, jobs, target_role, target_seniority, target_locations
        )
        for key, jobs in cached_results.items()
    ]
    match_results = await asyncio.gather(*match_tasks)
    recommendations = [r for r in match_results if r is not None]

    # Derive a single location hint for fallback fetchers (JobSpy / Adzuna)
    location_hint = target_locations[0] if target_locations else None

    # Phase 3: Only fetch fresh data if we don't have enough results.
    # Use a tight timeout so we never block longer than _FETCH_TIMEOUT.
    fresh_scanned = 0
    max_scan = settings.RECOMMENDATION_MAX_SCAN

    if len(recommendations) < max_results and uncached:
        to_fetch = uncached[:max_scan]
        fresh_recs, fresh_scanned = await _fetch_fresh_and_match(
            to_fetch,
            fetcher,
            target_role,
            target_seniority,
            location_hint,
            db,
            target_locations=target_locations,
        )
        recommendations.extend(fresh_recs)
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

    # Re-score: network + location + job relevance + ATS quality
    matched_regions = _resolve_regions(target_locations)
    max_density = max((r["network_density"] for r in merged), default=1) or 1
    for rec in merged:
        nd = rec["network_density"] / max_density  # normalize 0-1
        loc = 1.0 if matched_regions and rec.get("region") in matched_regions else 0.0
        jr = min(rec.get("score", 0) / 100, 1.0)  # normalize 0-1
        aq = 1.0 if rec["source"] == "board_registry" else 0.0
        rec["score"] = round(nd * 0.4 + loc * 0.3 + jr * 0.2 + aq * 0.1, 3)

    merged.sort(key=lambda r: r["score"], reverse=True)
    merged = merged[:max_results]

    # Mark companies where user has direct contacts as "referral ready"
    for rec in merged:
        rec["referral_ready"] = rec.get("own_contacts", 0) >= 1

    network_count = sum(1 for r in merged if r.get("network_density", 0) > 0)

    # --- Demand signal capture: log when results are sparse ---
    if len(merged) < 3:
        from app.models.marketplace import RecommendationDemandSignal

        signal = RecommendationDemandSignal(
            company_name=target_role.lower(),
            target_role=target_role,
            target_location=target_locations[0] if target_locations else None,
            user_id=user_id,
        )
        db.add(signal)
        await db.flush()
        logger.info(
            "Demand signal captured: role=%s location=%s user=%s (only %d results)",
            target_role,
            target_locations,
            user_id,
            len(merged),
        )

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

            warm_location_hint = locations[0] if locations else None
            fetcher = JobFetcher()
            semaphore = asyncio.Semaphore(5)
            tasks = [
                _fetch_jobs(
                    key,
                    BOARD_REGISTRY.get(key, {}),
                    fetcher,
                    semaphore,
                    location_hint=warm_location_hint,
                )
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
