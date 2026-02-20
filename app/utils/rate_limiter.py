"""Redis-based distributed rate limiter.

Uses a Redis list as a semaphore: BRPOP to acquire a slot, LPUSH to release.
Falls back to a local asyncio.Semaphore when Redis is unavailable (dev/test).

Designed as a generic utility — any service can create named limiters
(e.g. "anthropic", "resend") with independent concurrency limits.
"""

import asyncio
import logging

logger = logging.getLogger(__name__)

# Local fallback semaphores (keyed by limiter name)
_local_semaphores: dict[str, asyncio.Semaphore] = {}


def _get_redis_client():
    """Get async Redis client, or None if unavailable."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        return aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, max_connections=10
        )
    except Exception:
        logger.debug("Redis not available for rate limiter")
        return None


def _key(name: str) -> str:
    """Redis key for a named limiter."""
    return f"rate_limiter:{name}"


async def init_limiter(name: str, max_concurrent: int) -> None:
    """Ensure the limiter has the right number of tokens. Idempotent."""
    client = _get_redis_client()
    if not client:
        return
    try:
        key = _key(name)
        current = await client.llen(key)
        if current < max_concurrent:
            pipeline = client.pipeline()
            for _ in range(max_concurrent - current):
                pipeline.lpush(key, "1")
            await pipeline.execute()
            logger.info(
                "Rate limiter '%s': topped up %d tokens (now %d)",
                name,
                max_concurrent - current,
                max_concurrent,
            )
    except Exception:
        logger.debug("Failed to init rate limiter '%s'", name, exc_info=True)
    finally:
        await client.aclose()


async def acquire_slot(name: str, max_concurrent: int = 5, timeout: int = 60) -> bool:
    """Acquire a slot from the named limiter.

    Args:
        name: Limiter name (e.g. "anthropic").
        max_concurrent: Used for init and local fallback.
        timeout: Max seconds to wait for a slot.

    Returns:
        True if using Redis limiter, False if using local fallback.
        Raises asyncio.TimeoutError if timeout exceeded with local fallback.
    """
    client = _get_redis_client()
    if not client:
        # Local fallback
        if name not in _local_semaphores:
            _local_semaphores[name] = asyncio.Semaphore(max_concurrent)
        await asyncio.wait_for(_local_semaphores[name].acquire(), timeout=timeout)
        return False

    try:
        # Ensure tokens exist
        key = _key(name)
        current = await client.llen(key)
        if current == 0:
            await init_limiter(name, max_concurrent)

        result = await client.brpop(key, timeout=timeout)
        if result is None:
            logger.warning(
                "Rate limiter '%s': timeout after %ds waiting for slot", name, timeout
            )
            raise TimeoutError(f"Rate limiter '{name}' exhausted (timeout={timeout}s)")
        return True
    except TimeoutError:
        raise
    except Exception:
        logger.debug("Redis rate limiter failed, using local fallback", exc_info=True)
        if name not in _local_semaphores:
            _local_semaphores[name] = asyncio.Semaphore(max_concurrent)
        await asyncio.wait_for(_local_semaphores[name].acquire(), timeout=timeout)
        return False
    finally:
        await client.aclose()


async def release_slot(name: str, used_redis: bool) -> None:
    """Release a slot back to the named limiter.

    Args:
        name: Limiter name.
        used_redis: True if acquire_slot returned True (Redis path).
    """
    if not used_redis:
        # Local fallback
        sem = _local_semaphores.get(name)
        if sem:
            sem.release()
        return

    client = _get_redis_client()
    if not client:
        return
    try:
        await client.lpush(_key(name), "1")
    except Exception:
        logger.warning(
            "Failed to release rate limiter slot '%s' — token may be lost",
            name,
            exc_info=True,
        )
    finally:
        await client.aclose()


def top_up_tokens_sync(name: str, max_concurrent: int) -> None:
    """Sync wrapper for token top-up — called from Celery Beat watchdog.

    Recovers tokens lost to worker crashes by ensuring the list
    has exactly max_concurrent tokens available.
    """
    try:
        import redis

        from app.config import settings

        client = redis.from_url(
            settings.REDIS_URL, decode_responses=True, max_connections=2
        )
        key = _key(name)
        current = client.llen(key)
        if current < max_concurrent:
            deficit = max_concurrent - current
            pipe = client.pipeline()
            for _ in range(deficit):
                pipe.lpush(key, "1")
            pipe.execute()
            logger.info(
                "Watchdog: topped up %d tokens for '%s' (was %d, now %d)",
                deficit,
                name,
                current,
                max_concurrent,
            )
        client.close()
    except Exception:
        logger.debug("Watchdog token top-up failed for '%s'", name, exc_info=True)


async def get_queue_depth(queue_name: str = "celery") -> int:
    """Check Celery task queue depth via Redis LLEN.

    Returns 0 if Redis is unavailable (safe default — no degradation).
    """
    client = _get_redis_client()
    if not client:
        return 0
    try:
        depth = await client.llen(queue_name)
        return depth or 0
    except Exception:
        return 0
    finally:
        await client.aclose()
