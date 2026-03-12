"""Celery queue latency metrics collection.

Checks Redis for queue depths and estimates task latency.
Used by the perf dashboard and the existing monitor_tasks.py health checks.
"""

import logging
import time

logger = logging.getLogger(__name__)

# Alert thresholds
QUEUE_DEPTH_WARNING = 50
QUEUE_DEPTH_CRITICAL = 200
LATENCY_WARNING_MS = 30_000  # 30 seconds
LATENCY_CRITICAL_MS = 120_000  # 2 minutes


def collect_celery_metrics() -> dict:
    """Collect Celery queue metrics from Redis.

    Returns dict with queue depths, estimated latency, and alert levels.
    """
    try:
        import redis

        from app.config import settings

        r = redis.from_url(settings.REDIS_URL)

        # Check known Celery queues
        queues = ["celery", "csv_processing", "email", "feed"]
        queue_stats = {}

        for queue_name in queues:
            depth = r.llen(queue_name) or 0

            # Determine alert level
            if depth >= QUEUE_DEPTH_CRITICAL:
                alert = "critical"
            elif depth >= QUEUE_DEPTH_WARNING:
                alert = "warning"
            else:
                alert = "ok"

            queue_stats[queue_name] = {
                "depth": depth,
                "alert": alert,
            }

        # Check active/reserved tasks via inspect
        total_depth = sum(q["depth"] for q in queue_stats.values())

        # Estimate latency from oldest task age (if available)
        # This is a rough estimate based on queue depth and avg processing time
        estimated_latency_ms = None
        try:
            # Peek at oldest message in default queue
            oldest = r.lindex("celery", -1)
            if oldest:
                import json as _json

                msg = _json.loads(oldest)
                if "headers" in msg and "timestamp" in msg["headers"]:
                    age_s = time.time() - msg["headers"]["timestamp"]
                    estimated_latency_ms = round(age_s * 1000)
        except Exception:
            pass

        # Overall alert
        alerts = [q["alert"] for q in queue_stats.values()]
        if "critical" in alerts:
            overall_alert = "critical"
        elif "warning" in alerts:
            overall_alert = "warning"
        else:
            overall_alert = "ok"

        r.close()

        return {
            "queues": queue_stats,
            "total_depth": total_depth,
            "estimated_latency_ms": estimated_latency_ms,
            "overall_alert": overall_alert,
        }
    except Exception as e:
        logger.warning("Failed to collect Celery metrics: %s", e)
        return {
            "queues": {},
            "total_depth": 0,
            "estimated_latency_ms": None,
            "overall_alert": "unknown",
            "error": str(e),
        }
