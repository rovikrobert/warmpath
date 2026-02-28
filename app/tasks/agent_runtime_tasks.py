"""Agent runtime Celery tasks.

Periodic tasks for the agent runtime — Railway log polling, etc.
"""

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.agent_runtime_tasks.poll_[RAILWAY_TOKEN_REDACTED]")
def poll_[RAILWAY_TOKEN_REDACTED]() -> None:
    """Poll Railway logs for errors and dispatch to agent runtime stream."""
    from app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED] import (
        poll_[RAILWAY_TOKEN_REDACTED] as _poll,
    )

    _poll()
