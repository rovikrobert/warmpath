import logging
from typing import Any

from fastapi import APIRouter, Query

from app.utils.performance import THRESHOLDS, get_recent_metrics, get_stats

logger = logging.getLogger(__name__)

router = APIRouter()


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
        "data": {"status": "healthy", "celery": celery_status},
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
