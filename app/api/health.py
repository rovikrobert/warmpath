import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.utils.performance import THRESHOLDS, get_recent_metrics, get_stats

logger = logging.getLogger(__name__)

router = APIRouter()

# Top-level status values returned by /health.
# - healthy:   every critical dependency is reachable.
# - degraded:  every CRITICAL dep is reachable but at least one non-critical
#              dep is degraded/unavailable. Returns 200 so load balancers keep
#              the instance in the pool — operators see the degradation.
# - unhealthy: at least one critical dependency is unreachable. Returns 503
#              so load balancers can eject the instance.
_HEALTHY = "healthy"
_DEGRADED = "degraded"
_UNHEALTHY = "unhealthy"


def _frontend_version() -> str:
    """Derive frontend version from index.html asset hash."""
    index = Path("frontend/dist/index.html")
    if not index.exists():
        return "unknown"
    content = index.read_bytes()
    return hashlib.md5(content).hexdigest()[:8]


async def _check_db() -> dict[str, Any]:
    """Run a SELECT 1 against the configured database (critical)."""
    from app.database import _get_engine

    start = time.monotonic()
    try:
        engine = _get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }
    except Exception as exc:
        logger.warning("Health check: database unreachable", exc_info=True)
        return {
            "status": "unavailable",
            "error": type(exc).__name__,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }


def _check_celery() -> dict[str, Any]:
    """Ping Celery workers via the broker (non-critical)."""
    start = time.monotonic()
    try:
        from app.celery_app import celery_app

        replies = celery_app.control.ping(timeout=2.0) or []
        latency_ms = round((time.monotonic() - start) * 1000, 2)
        if replies:
            return {
                "status": "ok",
                "latency_ms": latency_ms,
                "workers": len(replies),
            }
        # Broker reachable but zero workers — degraded, not unavailable.
        return {
            "status": "degraded",
            "latency_ms": latency_ms,
            "workers": 0,
            "error": "no workers responded",
        }
    except Exception as exc:
        logger.warning("Health check: Celery ping failed", exc_info=True)
        return {
            "status": "unavailable",
            "error": type(exc).__name__,
            "latency_ms": round((time.monotonic() - start) * 1000, 2),
        }


def _roll_up_status(checks: dict[str, dict[str, Any]], critical: set[str]) -> str:
    """Roll dependency-level status into the overall health status."""
    for name in critical:
        if checks.get(name, {}).get("status") != "ok":
            return _UNHEALTHY
    if any(c.get("status") != "ok" for c in checks.values()):
        return _DEGRADED
    return _HEALTHY


@router.get("/health")
async def health_check() -> JSONResponse:
    """Application health check — DB (critical) + Celery (non-critical).

    Response shape (additive vs the prior version — all old fields preserved):

        {
          "data": {
            "status": "healthy" | "degraded" | "unhealthy",
            "celery": "connected" | "unavailable",     # legacy compat
            "frontend_version": "<hash>",
            "checks": {
              "db":     {"status": "ok"|"unavailable", "latency_ms": ..., "error"?: ...},
              "celery": {"status": "ok"|"degraded"|"unavailable", "latency_ms": ...,
                          "workers"?: ..., "error"?: ...}
            }
          },
          "meta": {}
        }

    HTTP status: 200 for healthy/degraded, 503 for unhealthy. The 503 lets
    load balancers and k8s readiness probes eject the instance.
    """
    db_check = await _check_db()
    celery_check = _check_celery()
    checks = {"db": db_check, "celery": celery_check}

    # DB is critical; Celery is non-critical (worker can be down without
    # breaking the synchronous API surface). Adjust the set when adding deps.
    overall = _roll_up_status(checks, critical={"db"})

    payload = {
        "data": {
            "status": overall,
            # Legacy field kept for backwards-compat with existing consumers.
            "celery": "connected" if celery_check["status"] == "ok" else "unavailable",
            "frontend_version": _frontend_version(),
            "checks": checks,
        },
        "meta": {},
    }
    http_status = 503 if overall == _UNHEALTHY else 200
    return JSONResponse(status_code=http_status, content=payload)


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
