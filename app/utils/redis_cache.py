"""Lightweight Redis response cache for expensive read endpoints.

Usage:
    from app.utils.redis_cache import cached_response

    @router.get("/expensive")
    async def expensive_endpoint(...):
        cache_key = f"credits:balance:{user_id}"
        cached = await cached_response(cache_key)
        if cached is not None:
            return cached

        # ... compute result ...
        result = {"data": ..., "meta": ...}
        await set_cached_response(cache_key, result, ttl_seconds=60)
        return result
"""

import json
import logging

logger = logging.getLogger(__name__)


async def _get_redis():
    """Get async Redis connection. Returns None if unavailable."""
    try:
        import redis.asyncio as aioredis

        from app.config import settings

        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await client.ping()
        return client
    except Exception:
        return None


async def cached_response(cache_key: str) -> dict | None:
    """Retrieve a cached response dict. Returns None on miss or error."""
    try:
        client = await _get_redis()
        if client is None:
            return None
        raw = await client.get(f"rcache:{cache_key}")
        await client.aclose()
        if raw is None:
            return None
        return json.loads(raw)
    except Exception:
        logger.debug("Cache miss (error) for %s", cache_key, exc_info=True)
        return None


async def set_cached_response(
    cache_key: str, data: dict, ttl_seconds: int = 60
) -> None:
    """Store a response dict in Redis with TTL."""
    try:
        client = await _get_redis()
        if client is None:
            return
        await client.set(
            f"rcache:{cache_key}", json.dumps(data, default=str), ex=ttl_seconds
        )
        await client.aclose()
    except Exception:
        logger.debug("Cache set failed for %s", cache_key, exc_info=True)


async def invalidate_cache(cache_key: str) -> None:
    """Delete a specific cache entry."""
    try:
        client = await _get_redis()
        if client is None:
            return
        await client.delete(f"rcache:{cache_key}")
        await client.aclose()
    except Exception:
        pass
