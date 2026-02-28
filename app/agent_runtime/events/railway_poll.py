"""Celery task: poll Railway logs for errors, dispatch to agent runtime."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess

from app.agent_runtime.events.ingestion import create_event
from app.agent_runtime.events.railway import parse_error_logs, should_alert
from app.utils.redis_streams import stream_add

logger = logging.getLogger(__name__)


def _fetch_recent_logs() -> list[str]:
    """Fetch recent Railway logs via CLI. Returns list of log lines."""
    try:
        result = subprocess.run(
            ["railway", "logs"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout.strip().splitlines() if result.stdout else []
    except Exception:
        logger.debug("Failed to fetch Railway logs", exc_info=True)
        return []


async def poll_railway_logs_async() -> None:
    """Async core: parse logs, create events, dispatch to stream."""
    log_lines = _fetch_recent_logs()
    if not log_lines:
        return

    parsed = parse_error_logs(log_lines)
    error_count = parsed["error_count"]

    if not should_alert(error_count):
        return

    event = create_event(
        event_type="incident",
        source="railway",
        payload={
            "error_count": error_count,
            "sample_errors": parsed["sample_errors"],
        },
        payload_key=f"railway-poll-{error_count}",
    )

    await stream_add("warmpath:agent_events", {"event": json.dumps(event)})
    logger.info("Railway poll dispatched incident event: %d errors", error_count)


def poll_railway_logs() -> None:
    """Sync wrapper for Celery task execution."""
    asyncio.run(poll_railway_logs_async())
