"""Infrastructure maintenance tasks.

Lightweight Celery tasks for platform health — rate limiter watchdog, etc.
"""

import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.infra_tasks.rate_limiter_watchdog")
def rate_limiter_watchdog() -> None:
    """Top up rate limiter tokens lost to worker crashes.

    Runs every 5 minutes via Beat. Ensures the Anthropic rate limiter
    always has the configured number of tokens available.
    """
    from app.utils.rate_limiter import top_up_tokens_sync

    top_up_tokens_sync("anthropic", settings.ANTHROPIC_MAX_CONCURRENT)
    if settings.CLEANUP_PROVIDER == "gemini":
        top_up_tokens_sync("gemini", settings.GOOGLE_MAX_CONCURRENT)
    logger.debug("Rate limiter watchdog completed")
