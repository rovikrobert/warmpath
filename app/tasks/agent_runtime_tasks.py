"""Agent runtime Celery tasks.

Periodic tasks for the agent runtime — Railway log polling, scheduled scans,
KPI anomaly detection, etc.
"""

import asyncio
import json
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.agent_runtime_tasks.poll_[RAILWAY_TOKEN_REDACTED]")
def poll_[RAILWAY_TOKEN_REDACTED]() -> None:
    """Poll Railway logs for errors and dispatch to agent runtime stream."""
    try:
        from app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED] import (
            poll_[RAILWAY_TOKEN_REDACTED] as _poll,
        )

        _poll()
    except Exception as exc:
        logger.exception("poll_[RAILWAY_TOKEN_REDACTED] failed")
        try:
            import asyncio

            from app.utils.task_escalation import escalate_task_failure

            asyncio.run(
                escalate_task_failure(
                    task_name="poll_[RAILWAY_TOKEN_REDACTED]", error=exc, severity="medium"
                )
            )
        except Exception:
            logger.warning("Railway poll escalation failed")


@celery_app.task(name="app.tasks.agent_runtime_tasks.dispatch_scheduled_scan")
def dispatch_scheduled_scan(cadence: str = "daily") -> None:
    """Dispatch a scheduled scan event to the agent runtime stream.

    Args:
        cadence: "daily" (engineering only) or "weekly" (all 6 teams).
    """
    from app.config import settings

    if not settings.AGENT_RUNTIME_ENABLED:
        logger.info("Agent runtime disabled, skipping scheduled scan")
        return

    try:
        from app.agent_runtime.events.ingestion import create_event
        from app.utils.redis_streams import stream_add

        event = create_event(
            event_type="scheduled_scan",
            source="celery_beat",
            payload={"cadence": cadence},
            payload_key=f"scheduled_{cadence}",
        )
        asyncio.run(stream_add("warmpath:agent_events", {"event": json.dumps(event)}))
        logger.info("Dispatched %s scheduled scan event", cadence)
    except Exception as exc:
        logger.exception("dispatch_scheduled_scan failed")
        try:
            from app.utils.task_escalation import escalate_task_failure

            asyncio.run(
                escalate_task_failure(
                    task_name="dispatch_scheduled_scan",
                    error=exc,
                    severity="medium",
                )
            )
        except Exception:
            logger.warning("Scheduled scan escalation failed")


@celery_app.task(name="app.tasks.agent_runtime_tasks.dispatch_kpi_check")
def dispatch_kpi_check() -> None:
    """Run KPI anomaly detection and dispatch alerts as agent_finding events."""
    from app.config import settings

    if not settings.AGENT_RUNTIME_ENABLED:
        logger.info("Agent runtime disabled, skipping KPI check")
        return

    try:
        from app.agent_runtime.events.ingestion import create_event
        from app.agent_runtime.kpi_monitor import check_all_kpis
        from app.utils.redis_streams import stream_add

        anomalies = asyncio.run(check_all_kpis())

        if anomalies:
            from app.agent_runtime.notifications import notify_kpi_anomaly

            asyncio.run(
                notify_kpi_anomaly(
                    anomalies=[
                        {
                            "severity": a["severity"],
                            "metric": a["metric"],
                            "value": f"{a['current_value']:.2f}"
                            if isinstance(a["current_value"], float)
                            else str(a["current_value"]),
                        }
                        for a in anomalies
                    ],
                    redis_url=settings.REDIS_URL,
                )
            )

        for anomaly in anomalies:
            event = create_event(
                event_type="agent_finding",
                source="kpi_monitor",
                payload={
                    "category": "kpi_anomaly",
                    "severity": anomaly["severity"],
                    "metric": anomaly["metric"],
                    "current_value": anomaly["current_value"],
                    "expected_range": anomaly["expected_range"],
                    "description": anomaly["description"],
                },
                payload_key=f"kpi_{anomaly['metric']}",
            )
            asyncio.run(
                stream_add("warmpath:agent_events", {"event": json.dumps(event)})
            )
            logger.info("KPI anomaly dispatched: %s", anomaly["metric"])
    except Exception as exc:
        logger.exception("dispatch_kpi_check failed")
        try:
            from app.utils.task_escalation import escalate_task_failure

            asyncio.run(
                escalate_task_failure(
                    task_name="dispatch_kpi_check",
                    error=exc,
                    severity="high",
                )
            )
        except Exception:
            logger.warning("KPI check escalation failed")
