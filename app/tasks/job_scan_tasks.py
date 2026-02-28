"""Celery tasks for background job cache warming.

Pre-warms job caches for all registered companies so that recommendation
endpoints serve entirely from cache with no user-facing latency.
"""

import asyncio
import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


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

            async def _fetch_one(company_key: str, boards: dict[str, str]) -> int:
                async with semaphore:
                    try:
                        jobs = await fetcher.fetch_jobs_for_company(company_key, boards)
                        cache_key = f"job_scan:{company_key}"
                        job_data = {
                            "company": company_key,
                            "job_count": len(jobs),
                            "jobs": jobs[:100],  # Cap stored jobs
                            "scanned_at": now.isoformat(),
                        }
                        result = await db.execute(
                            select(EnrichmentCache).where(
                                EnrichmentCache.cache_key == cache_key
                            )
                        )
                        cached = result.scalar_one_or_none()
                        if cached is not None:
                            cached.data = job_data
                            cached.expires_at = now + ttl
                        else:
                            cached = EnrichmentCache(
                                cache_key=cache_key,
                                source="job_scan",
                                data=job_data,
                                expires_at=now + ttl,
                            )
                            db.add(cached)
                        await db.flush()
                        return len(jobs)
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

            # Trigger vector sync for jobs
            if settings.VECTOR_SEARCH_ENABLED:
                from app.tasks.vector_tasks import sync_all_jobs

                sync_all_jobs.delay()

            return total

    return _run_async(_run())
