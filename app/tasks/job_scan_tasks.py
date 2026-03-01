"""Celery tasks for background job cache warming.

Pre-warms job caches for all registered companies so that recommendation
endpoints serve entirely from cache with no user-facing latency.
Detects anomalies (SPA scrape failures, ATS API failures, major drops,
total zeros) and alerts via FindingStore + Telegram.
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

# Minimum jobs expected from a career page scrape — below this suggests
# the page is a JavaScript SPA that httpx can't render.
_SPA_SCRAPE_THRESHOLD = 5

# If new job count drops below this fraction of previous count, flag it.
_MAJOR_DROP_RATIO = 1 / 3


def _run_async(coro):
    """Bridge async code into sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _dispose_stale_pool():
    """Dispose stale asyncpg connections before each Celery task."""
    from app.database import _get_engine

    await _get_engine().dispose()


def _get_session_factory():
    """Create an async session factory for Celery tasks."""
    from app.database import _get_session_factory

    return _get_session_factory()


def _detect_job_anomaly(
    company_key: str,
    boards: dict[str, str],
    job_count: int,
    prev_count: int,
) -> dict | None:
    """Check a single company's fetch result against the 4 anomaly rules.

    Returns a finding dict suitable for FindingStore, or None.
    """
    has_ats = bool({"greenhouse", "lever", "ashby"} & set(boards))
    has_career_page = "career_page" in boards

    # Rule 1: ATS API failure — board registered but returned nothing
    if has_ats and job_count == 0:
        return {
            "source_team": "engineering",
            "category": "job_scan_anomaly",
            "title": f"{company_key}: ATS API returned 0 jobs",
            "severity": "high",
        }

    # Rule 2: SPA scrape failure — career page returned suspiciously few
    if has_career_page and not has_ats and 0 < job_count < _SPA_SCRAPE_THRESHOLD:
        return {
            "source_team": "engineering",
            "category": "job_scan_anomaly",
            "title": f"{company_key}: career page scrape returned only {job_count} jobs",
            "severity": "medium",
        }

    # Rule 3: Major drop — new count is less than 1/3 of previous
    if prev_count >= 10 and job_count < prev_count * _MAJOR_DROP_RATIO:
        return {
            "source_team": "engineering",
            "category": "job_scan_anomaly",
            "title": f"{company_key}: job count dropped {prev_count} → {job_count}",
            "severity": "high",
        }

    # Rule 4: Total zero — company in registry but got nothing at all
    if job_count == 0 and not has_ats:
        return {
            "source_team": "engineering",
            "category": "job_scan_anomaly",
            "title": f"{company_key}: 0 jobs from all sources",
            "severity": "medium",
        }

    return None


async def _dispatch_anomalies(anomalies: list[dict]) -> None:
    """Feed anomalies into FindingStore and send Telegram alert for new ones."""
    redis_url = settings.REDIS_URL
    if not redis_url:
        logger.warning("REDIS_URL not set — skipping anomaly dispatch")
        return

    from app.agent_runtime.finding_store import FindingStore
    from app.agent_runtime.notifications import notify_job_scan_anomalies

    store = FindingStore(redis_url=redis_url)
    new_findings, known_findings = await store.classify_findings(anomalies)

    logger.info(
        "Job scan anomalies: %d new, %d known",
        len(new_findings),
        len(known_findings),
    )

    # Only alert on new findings (known ones have been seen before)
    if new_findings:
        await notify_job_scan_anomalies(new_findings, redis_url)


@celery_app.task(name="app.tasks.job_scan_tasks.warm_job_cache_global")
def warm_job_cache_global():
    """Pre-warm job cache for all registered companies.

    Fetches jobs for every company in BOARD_REGISTRY and stores results
    in EnrichmentCache with a 6h TTL. Uses a semaphore to limit concurrent
    HTTP requests (5 at a time).

    Schedule: Every 4 hours via Celery Beat.
    """

    async def _run():
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.models.enrichment import EnrichmentCache
        from app.services.board_registry import BOARD_REGISTRY
        from app.services.job_fetcher import JobFetcher

        await _dispose_stale_pool()
        fetcher = JobFetcher()
        semaphore = asyncio.Semaphore(5)
        now = datetime.now(timezone.utc)
        ttl = timedelta(hours=6)
        companies = list(BOARD_REGISTRY.items())

        async with _get_session_factory()() as db:
            # Check which companies need refreshing
            to_fetch: list[tuple[str, dict[str, str]]] = []
            for company_key, boards in companies:
                cache_key = f"job_scan:{company_key}"
                result = await db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.cache_key == cache_key
                    )
                )
                cached = result.scalar_one_or_none()
                if cached is not None and cached.expires_at > now:
                    continue  # Still fresh
                to_fetch.append((company_key, boards))

            logger.info(
                "Job cache warming: %d/%d companies need refresh",
                len(to_fetch),
                len(companies),
            )

            if not to_fetch:
                return 0

            all_anomalies: list[dict] = []

            async def _fetch_one(company_key: str, boards: dict[str, str]) -> int:
                async with semaphore:
                    try:
                        jobs = await fetcher.fetch_jobs_for_company(company_key, boards)
                        job_count = len(jobs)
                        cache_key = f"job_scan:{company_key}"

                        # --- Anomaly detection ---
                        # Read previous cache for major-drop comparison
                        prev_result = await db.execute(
                            select(EnrichmentCache).where(
                                EnrichmentCache.cache_key == cache_key
                            )
                        )
                        prev_cached = prev_result.scalar_one_or_none()
                        prev_count = (
                            prev_cached.data.get("job_count", 0)
                            if prev_cached is not None and prev_cached.data
                            else 0
                        )

                        anomaly = _detect_job_anomaly(
                            company_key, boards, job_count, prev_count
                        )
                        if anomaly:
                            all_anomalies.append(anomaly)

                        # --- Cache write ---
                        job_data = {
                            "company": company_key,
                            "job_count": job_count,
                            "jobs": jobs[:100],  # Cap stored jobs
                            "scanned_at": now.isoformat(),
                        }
                        if prev_cached is not None:
                            prev_cached.data = job_data
                            prev_cached.expires_at = now + ttl
                        else:
                            prev_cached = EnrichmentCache(
                                cache_key=cache_key,
                                source="job_scan",
                                data=job_data,
                                expires_at=now + ttl,
                            )
                            db.add(prev_cached)
                        await db.flush()
                        return job_count
                    except Exception:
                        logger.exception(
                            "Job cache warming failed for '%s'", company_key
                        )
                        return 0

            results = await asyncio.gather(
                *[_fetch_one(key, boards) for key, boards in to_fetch]
            )
            total = sum(results)
            await db.commit()
            logger.info(
                "Job cache warming complete: %d jobs cached for %d companies",
                total,
                len(to_fetch),
            )

            # --- Dispatch anomalies ---
            if all_anomalies:
                await _dispatch_anomalies(all_anomalies)

            # Trigger vector sync for jobs
            if settings.VECTOR_SEARCH_ENABLED:
                from app.tasks.vector_tasks import sync_all_jobs

                sync_all_jobs.delay()

            return total

    return _run_async(_run())
