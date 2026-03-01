"""KPI anomaly detection for the agent runtime.

Tracks key metrics in Redis and detects significant deviations.
Anomalies are dispatched as agent_finding events.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import statistics
from typing import Any

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

PREFIX = "agentrt:kpi"
# Keep 30 days of daily samples
HISTORY_MAX_LEN = 30


async def _get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def record_metric(metric: str, value: float) -> None:
    """Append a daily metric value to the time series."""
    r = await _get_redis()
    key = f"{PREFIX}:{metric}"
    await r.rpush(key, str(value))
    await r.ltrim(key, -HISTORY_MAX_LEN, -1)
    await r.aclose()


async def get_history(metric: str) -> list[float]:
    """Retrieve metric history."""
    r = await _get_redis()
    values = await r.lrange(f"{PREFIX}:{metric}", 0, -1)
    await r.aclose()
    return [float(v) for v in values]


def _detect_anomaly(
    values: list[float], current: float, metric: str
) -> dict[str, Any] | None:
    """Detect if current value is anomalous (>2σ from mean).

    Returns anomaly dict or None if within normal range.
    Requires at least 5 data points for meaningful statistics.
    """
    if len(values) < 5:
        return None

    mean = statistics.mean(values)
    stdev = statistics.stdev(values)

    if stdev == 0:
        # No variance — any deviation is anomalous
        if current != mean:
            return {
                "metric": metric,
                "current_value": current,
                "expected_range": f"{mean:.1f} (no variance)",
                "severity": "medium",
                "description": f"{metric} changed from constant {mean:.1f} to {current:.1f}",
            }
        return None

    z_score = abs(current - mean) / stdev

    if z_score > 3:
        severity = "high"
    elif z_score > 2:
        severity = "medium"
    else:
        return None

    direction = "increased" if current > mean else "decreased"
    return {
        "metric": metric,
        "current_value": current,
        "expected_range": f"{mean - 2 * stdev:.1f} to {mean + 2 * stdev:.1f}",
        "severity": severity,
        "description": f"{metric} {direction} to {current:.1f} (mean: {mean:.1f}, z-score: {z_score:.1f})",
    }


async def _collect_current_metrics() -> dict[str, float]:
    """Collect current values for tracked KPIs."""
    metrics: dict[str, float] = {}

    try:
        r = await _get_redis()
        # Daily agent runtime spend
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        spend = await r.get(f"agentrt:spend:{today}")
        metrics["daily_agent_spend_usd"] = float(spend) if spend else 0.0
        await r.aclose()
    except Exception:
        logger.debug("Failed to collect spend metric", exc_info=True)

    try:
        # Finding store stats (if available)
        from app.agent_runtime.finding_store import FindingStore

        store = FindingStore(redis_url=settings.REDIS_URL)
        stats = await store.get_stats()
        metrics["open_findings"] = float(stats.get("new", 0) + stats.get("known", 0))
    except Exception:
        logger.debug("Failed to collect finding stats", exc_info=True)

    return metrics


async def check_all_kpis() -> list[dict[str, Any]]:
    """Run anomaly detection on all tracked KPIs.

    Returns list of anomaly dicts (may be empty if all normal).
    """
    anomalies: list[dict[str, Any]] = []
    current_metrics = await _collect_current_metrics()

    for metric, current_value in current_metrics.items():
        history = await get_history(metric)

        anomaly = _detect_anomaly(history, current_value, metric)
        if anomaly:
            anomalies.append(anomaly)

        # Record current value for future comparison
        await record_metric(metric, current_value)

    return anomalies
