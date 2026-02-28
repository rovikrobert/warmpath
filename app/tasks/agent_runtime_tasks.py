"""Agent runtime Celery tasks.

Periodic tasks for the agent runtime — Railway log polling, etc.
"""

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
