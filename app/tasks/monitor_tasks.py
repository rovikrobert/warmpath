"""Celery task for continuous production monitoring."""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="monitor.run_health_check", igno[RESEND_KEY_REDACTED]=True)
def run_monitor_check() -> dict:
    """Run all health checks. Triggered every 5 minutes by Beat."""
    from agents.monitor.monitor import MonitorConfig, run_health_checks

    config = MonitorConfig()
    report = run_health_checks(config)

    if not report.all_healthy and not config.calibration_mode:
        try:
            import os

            import redis

            from agents.shared.event_stream import format_event

            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.from_url(redis_url)
                for check in report.checks:
                    if not check.healthy:
                        event = format_event(
                            team="engineering",
                            agent="monitor",
                            action="escalated",
                            detail=f"{check.source}: {check.detail}",
                        )
                        r.xadd("cto:events", {k: str(v) for k, v in event.items()})
        except Exception as exc:
            logger.warning("Failed to publish monitor alert: %s", exc)

    return {
        "all_healthy": report.all_healthy,
        "checks": len(report.checks),
        "calibration_mode": config.calibration_mode,
    }


@celery_app.task(name="monitor.celery_backlog_check", igno[RESEND_KEY_REDACTED]=True)
def celery_backlog_check() -> dict:
    """Check Celery queue depths and alert on backlog thresholds.

    Triggered every 5 minutes by Beat. Publishes escalation events
    to the engineering Redis stream when queues exceed warning/critical levels.
    """
    from app.utils.celery_metrics import collect_celery_metrics

    metrics = collect_celery_metrics()

    if metrics["overall_alert"] in ("warning", "critical"):
        logger.warning(
            "CELERY_BACKLOG_%s: total_depth=%d, queues=%s",
            metrics["overall_alert"].upper(),
            metrics["total_depth"],
            {k: v["depth"] for k, v in metrics["queues"].items() if v["depth"] > 0},
        )

        # Escalate to engineering event stream
        try:
            import os

            import redis

            from agents.shared.event_stream import format_event

            redis_url = os.getenv("REDIS_URL")
            if redis_url:
                r = redis.from_url(redis_url)
                event = format_event(
                    team="engineering",
                    agent="monitor",
                    action="escalated",
                    detail=(
                        f"Celery backlog {metrics['overall_alert']}: "
                        f"total_depth={metrics['total_depth']}"
                    ),
                )
                r.xadd("cto:events", {k: str(v) for k, v in event.items()})
        except Exception as exc:
            logger.warning("Failed to publish backlog alert: %s", exc)

    return metrics
