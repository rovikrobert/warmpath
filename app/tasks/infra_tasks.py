"""Infrastructure maintenance tasks.

Lightweight Celery tasks for platform health — rate limiter watchdog,
Redis Stream cleanup, etc.
"""

import logging

from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.infra_tasks.rate_limiter_watchdog")
def rate_limiter_watchdog() -> None:
    """Top up rate limiter tokens lost to worker crashes.

    Runs every 5 minutes via Beat. Ensures all configured AI provider
    rate limiters have their tokens available.
    """
    from app.utils.rate_limiter import top_up_tokens_sync

    # Always top up Anthropic (used for matcher, scorer, coach — not just cleaner)
    top_up_tokens_sync("anthropic", settings.ANTHROPIC_MAX_CONCURRENT)

    # Top up all configured cleaning providers
    if settings.GOOGLE_API_KEY or settings.GOOGLE_SERVICE_ACCOUNT_JSON:
        top_up_tokens_sync("gemini", settings.GOOGLE_MAX_CONCURRENT)
    if settings.OPENAI_API_KEY:
        top_up_tokens_sync("openai", settings.OPENAI_MAX_CONCURRENT)
    if settings.GROQ_API_KEY:
        top_up_tokens_sync("groq", settings.GROQ_MAX_CONCURRENT)
    logger.debug("Rate limiter watchdog completed")


@celery_app.task(name="app.tasks.infra_tasks.redis_stream_janitor")
def redis_stream_janitor() -> None:
    """Clean up orphaned Redis Streams older than TTL.

    Runs every 30 minutes via Beat. Catches streams left behind by
    crashed pipeline tasks.
    """
    import asyncio

    asyncio.run(_janitor_async())


async def _janitor_async() -> None:
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            # Scan for csv: streams
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match="csv:*", count=100)
                for key in keys:
                    try:
                        info = await client.xinfo_stream(key)
                        length = info.get("length", 0)
                        # If stream is empty and has been idle, delete it
                        if length == 0:
                            await client.delete(key)
                            logger.info("Janitor: deleted empty stream %s", key)
                    except Exception:
                        # Stream might have been deleted between scan and info
                        pass
                if cursor == 0:
                    break
        finally:
            await client.aclose()
    except Exception:
        logger.debug("Stream janitor failed", exc_info=True)
