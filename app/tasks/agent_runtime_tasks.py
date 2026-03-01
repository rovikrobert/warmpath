"""Agent runtime Celery tasks.

Periodic tasks for the agent runtime — Railway log polling, scheduled scans,
KPI anomaly detection, etc.
"""

import asyncio
import json
import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.agent_runtime_tasks.poll_railway_logs")
def poll_railway_logs() -> None:
    """Poll Railway logs for errors and dispatch to agent runtime stream."""
    from app.agent_runtime.events.railway_poll import (
        poll_railway_logs as _poll,
    )

    _poll()


@celery_app.task(name="app.tasks.agent_runtime_tasks.dispatch_scheduled_scan")
def dispatch_scheduled_scan(cadence: str = "daily") -> None:
    """Dispatch a scheduled scan event to the agent runtime stream.

    Args:
        cadence: "daily" (engineering only) or "weekly" (all 6 teams).
    """
    from app.agent_runtime.events.ingestion import create_event
    from app.config import settings
    from app.utils.redis_streams import stream_add

    if not settings.AGENT_RUNTIME_ENABLED:
        logger.info("Agent runtime disabled, skipping scheduled scan")
        return

    event = create_event(
        event_type="scheduled_scan",
        source="celery_beat",
        payload={"cadence": cadence},
        payload_key=f"scheduled_{cadence}",
    )
    asyncio.get_event_loop().run_until_complete(
        stream_add("warmpath:agent_events", {"event": json.dumps(event)})
    )
    logger.info("Dispatched %s scheduled scan event", cadence)


@celery_app.task(name="app.tasks.agent_runtime_tasks.dispatch_kpi_check")
def dispatch_kpi_check() -> None:
    """Run KPI anomaly detection and dispatch alerts as agent_finding events."""
    from app.agent_runtime.events.ingestion import create_event
    from app.agent_runtime.kpi_monitor import check_all_kpis
    from app.config import settings
    from app.utils.redis_streams import stream_add

    if not settings.AGENT_RUNTIME_ENABLED:
        logger.info("Agent runtime disabled, skipping KPI check")
        return

    anomalies = asyncio.get_event_loop().run_until_complete(check_all_kpis())
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
        asyncio.get_event_loop().run_until_complete(
            stream_add("warmpath:agent_events", {"event": json.dumps(event)})
        )
        logger.info("KPI anomaly dispatched: %s", anomaly["metric"])
