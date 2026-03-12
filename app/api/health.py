import hashlib
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query

from app.utils.performance import THRESHOLDS, get_recent_metrics, get_stats

logger = logging.getLogger(__name__)

router = APIRouter()


def _frontend_version() -> str:
    """Derive frontend version from index.html asset hash."""
    index = Path("frontend/dist/index.html")
    if not index.exists():
        return "unknown"
    content = index.read_bytes()
    return hashlib.md5(content).hexdigest()[:8]


@router.get("/health")
def health_check() -> dict:
    """Application health check — verifies API + Celery connectivity."""
    celery_status = "unavailable"
    try:
        from app.celery_app import celery_app

        result = celery_app.control.ping(timeout=2.0)
        if result:
            celery_status = "connected"
    except Exception:
        logger.debug("Celery ping failed", exc_info=True)

    return {
        "data": {
            "status": "healthy",
            "celery": celery_status,
            "frontend_version": _frontend_version(),
        },
        "meta": {},
    }


@router.get("/health/perf")
def perf_stats(
    operation: str | None = Query(None, description="Filter by operation key"),
) -> dict[str, Any]:
    """Runtime performance statistics from in-memory ring buffer."""
    if operation:
        stats = get_stats(operation)
        return {"data": stats or {}, "meta": {"operation": operation}}

    # Return stats for all operations that have data
    all_stats: list[dict] = []
    seen: set[str] = set()
    for m in get_recent_metrics():
        if m["op"] not in seen:
            seen.add(m["op"])
    for op in sorted(seen):
        s = get_stats(op)
        if s:
            all_stats.append(s)

    return {
        "data": all_stats,
        "meta": {
            "total_operations": len(all_stats),
            "thresholds": THRESHOLDS,
        },
    }


@router.get("/health/perf/dashboard")
async def perf_dashboard() -> dict:
    """Combined performance dashboard: timings + DB stats + queue health.

    Aggregates data from multiple sources into a single overview.
    Designed for internal monitoring — no auth required (same as /health).
    """
    from app.utils.celery_metrics import collect_celery_metrics
    from app.utils.query_budgets import ENDPOINT_BUDGETS

    # 1. Backend timing stats (from ring buffer)
    seen_ops: set[str] = set()
    for m in get_recent_metrics():
        seen_ops.add(m["op"])

    timing_stats = []
    for op in sorted(seen_ops):
        s = get_stats(op)
        if s:
            timing_stats.append(s)

    # 2. Celery queue metrics
    celery_stats = collect_celery_metrics()

    # 3. Query budgets summary
    budgets = [{"method": m, "path": p, **b} for (m, p), b in ENDPOINT_BUDGETS.items()]

    # 4. Latest daily perf report (from DB cache)
    daily_report = None
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

        from app.database import _get_engine

        factory = async_sessionmaker(_get_engine(), class_=AsyncSession)
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT data FROM enrichment_cache "
                    "WHERE cache_key = 'perf_report_daily' "
                    "AND expires_at > NOW() LIMIT 1"
                )
            )
            row = result.first()
            if row:
                import json

                daily_report = json.loads(row[0])
    except Exception:
        pass

    return {
        "data": {
            "timing_stats": timing_stats,
            "celery": celery_stats,
            "query_budgets": budgets,
            "daily_report": daily_report,
        },
        "meta": {
            "operations_tracked": len(timing_stats),
            "thresholds": THRESHOLDS,
        },
    }
