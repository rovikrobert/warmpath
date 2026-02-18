"""Performance timing instrumentation.

Provides a `@timed` decorator that logs execution duration to structured logs
and optionally writes a UsageLog entry (action="perf") when a threshold is
exceeded. Thresholds are defined per operation key.

Usage:
    from app.utils.performance import timed

    @timed("ai_match")
    async def run_search(...):
        ...

    @timed("csv_process", threshold_ms=120_000)
    async def process_csv_upload_core(...):
        ...
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import functools
import inspect
import logging
import time
from typing import Any, Callable

logger = logging.getLogger("perf")

# ---------------------------------------------------------------------------
# Threshold config (ms) — industry best practices
# ---------------------------------------------------------------------------

THRESHOLDS: dict[str, int] = {
    # Search & AI matching
    "ai_match": 30_000,
    "ai_sco[RESEND_KEY_REDACTED]": 20_000,
    "ai_call_claude": 15_000,
    "ai_p[RESEND_KEY_REDACTED]": 2_000,
    "ai_mock_score": 1_000,
    "search_execute": 35_000,
    "search_results": 5_000,
    # CSV processing
    "csv_process": 120_000,
    "csv_parse": 10_000,
    "csv_upload_endpoint": 5_000,
    # Warm scoring
    "warm_sco[RESEND_KEY_REDACTED]": 30_000,
    "warm_sco[RESEND_KEY_REDACTED]": 100,
    # Intro drafting
    "intro_draft": 10_000,
    "intro_api_call": 8_000,
    "intro_mock": 500,
    # Coach
    "coach_briefing": 15_000,
    "coach_chat": 10_000,
    # Marketplace
    "marketplace_search": 8_000,
    "marketplace_generate_listings": 30_000,
    # Privacy / export
    "data_export": 60_000,
    "account_deletion": 120_000,
    "suppression_check": 100,
    # Jobs / recommendations
    "job_fetch": 45_000,
    "job_recommendations": 15_000,
    # Resume / enrichment
    "resume_parse": 10_000,
    # Auth
    "auth_signup": 5_000,
    "auth_login": 2_000,
    "auth_linkedin_exchange": 3_000,
    # DB-heavy list endpoints
    "contacts_list": 5_000,
    "applications_list": 5_000,
    "marketplace_my_listings": 3_000,
    # Credit operations
    "credits_balance": 1_000,
    "credits_purchase": 5_000,
    # Referral
    "referral_create": 2_000,
    "referral_redeem": 3_000,
    "referral_leaderboard": 2_000,
}

# Classification tiers for alerting
SEVERITY_TIERS = {
    "critical": 2.0,  # >2x threshold
    "warning": 1.0,   # >1x threshold
    "info": 0.5,      # >0.5x threshold (approaching)
}


def _get_threshold(operation: str, override_ms: int | None) -> int:
    """Resolve threshold: explicit override > config > default 10s."""
    if override_ms is not None:
        return override_ms
    return THRESHOLDS.get(operation, 10_000)


def _classify(duration_ms: float, threshold_ms: int) -> str:
    """Return severity tier based on duration vs threshold."""
    ratio = duration_ms / threshold_ms if threshold_ms > 0 else 0
    if ratio >= SEVERITY_TIERS["critical"]:
        return "critical"
    if ratio >= SEVERITY_TIERS["warning"]:
        return "warning"
    if ratio >= SEVERITY_TIERS["info"]:
        return "info"
    return "ok"


def _log_timing(
    operation: str,
    duration_ms: float,
    threshold_ms: int,
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit structured log for timing data."""
    severity = _classify(duration_ms, threshold_ms)
    exceeded = duration_ms > threshold_ms

    log_data = {
        "op": operation,
        "duration_ms": round(duration_ms, 1),
        "threshold_ms": threshold_ms,
        "exceeded": exceeded,
        "severity": severity,
    }
    if extra:
        log_data.update(extra)

    if severity == "critical":
        logger.warning(
            "PERF_CRITICAL: %s took %.0fms (threshold: %dms, %.0f%% over)",
            operation, duration_ms, threshold_ms,
            ((duration_ms / threshold_ms) - 1) * 100 if threshold_ms else 0,
            extra={"perf": log_data},
        )
    elif exceeded:
        logger.warning(
            "PERF_EXCEEDED: %s took %.0fms (threshold: %dms)",
            operation, duration_ms, threshold_ms,
            extra={"perf": log_data},
        )
    else:
        logger.info(
            "PERF: %s completed in %.0fms",
            operation, duration_ms,
            extra={"perf": log_data},
        )


# ---------------------------------------------------------------------------
# In-memory metrics ring buffer for runtime analysis
# ---------------------------------------------------------------------------

_BUFFER_SIZE = 2000
_metrics_buffer: list[dict[str, Any]] = []


def get_recent_metrics(operation: str | None = None, limit: int = 100) -> list[dict]:
    """Return recent timing metrics, optionally filtered by operation."""
    items = _metrics_buffer if not operation else [
        m for m in _metrics_buffer if m["op"] == operation
    ]
    return items[-limit:]


def get_stats(operation: str) -> dict[str, Any] | None:
    """Compute p50, p95, p99, avg, count for a given operation."""
    durations = [m["duration_ms"] for m in _metrics_buffer if m["op"] == operation]
    if not durations:
        return None
    durations.sort()
    n = len(durations)
    return {
        "operation": operation,
        "count": n,
        "avg_ms": round(sum(durations) / n, 1),
        "p50_ms": round(durations[n // 2], 1),
        "p95_ms": round(durations[int(n * 0.95)], 1) if n >= 20 else None,
        "p99_ms": round(durations[int(n * 0.99)], 1) if n >= 100 else None,
        "max_ms": round(max(durations), 1),
        "min_ms": round(min(durations), 1),
        "threshold_ms": THRESHOLDS.get(operation),
    }


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------

def timed(
    operation: str,
    threshold_ms: int | None = None,
) -> Callable:
    """Decorator that times function execution and logs results.

    Works with both sync and async functions. Timing data is:
    1. Logged via structured logger
    2. Stored in an in-memory ring buffer for runtime analysis
    3. Available via get_recent_metrics() and get_stats()

    Args:
        operation: Key identifying the operation (e.g. "ai_match").
        threshold_ms: Override the default threshold from THRESHOLDS config.
    """
    resolved_threshold = _get_threshold(operation, threshold_ms)

    def decorator(func: Callable) -> Callable:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.monotonic()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    _log_timing(operation, elapsed_ms, resolved_threshold)
                    entry = {
                        "op": operation,
                        "duration_ms": round(elapsed_ms, 1),
                        "threshold_ms": resolved_threshold,
                        "exceeded": elapsed_ms > resolved_threshold,
                        "ts": time.time(),
                    }
                    _metrics_buffer.append(entry)
                    if len(_metrics_buffer) > _BUFFER_SIZE:
                        _metrics_buffer.pop(0)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                t0 = time.monotonic()
                try:
                    return func(*args, **kwargs)
                finally:
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    _log_timing(operation, elapsed_ms, resolved_threshold)
                    entry = {
                        "op": operation,
                        "duration_ms": round(elapsed_ms, 1),
                        "threshold_ms": resolved_threshold,
                        "exceeded": elapsed_ms > resolved_threshold,
                        "ts": time.time(),
                    }
                    _metrics_buffer.append(entry)
                    if len(_metrics_buffer) > _BUFFER_SIZE:
                        _metrics_buffer.pop(0)
            return sync_wrapper
    return decorator
