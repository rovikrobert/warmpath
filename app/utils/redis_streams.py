"""Redis Streams helpers for the CSV processing pipeline.

Thin wrappers around XADD, XREADGROUP, XACK, and stream lifecycle.
Falls back gracefully when Redis is unavailable (dev/test).
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _get_redis_client():
    """Get async Redis client, or None if unavailable."""
    try:
        import redis.asyncio as aioredis
        from app.config import settings

        return aioredis.from_url(
            settings.REDIS_URL, decode_responses=True, max_connections=10
        )
    except Exception:
        logger.debug("Redis not available for streams")
        return None


def parsed_stream_key(upload_id: str) -> str:
    return f"csv:parsed:{upload_id}"


def cleaned_stream_key(upload_id: str) -> str:
    return f"csv:cleaned:{upload_id}"


async def stream_add(stream: str, fields: dict[str, str]) -> str | None:
    """Add a message to a Redis Stream. Returns message ID."""
    client = _get_redis_client()
    if not client:
        return None
    try:
        return await client.xadd(stream, fields)
    finally:
        await client.aclose()


async def ensu[RESEND_KEY_REDACTED](stream: str, group: str) -> None:
    """Create a consumer group if it doesn't exist. Idempotent."""
    client = _get_redis_client()
    if not client:
        return
    try:
        await client.xgroup_create(stream, group, id="0", mkstream=True)
    except Exception as e:
        if "BUSYGROUP" in str(e):
            pass  # Group already exists
        else:
            logger.warning(
                "Failed to create consumer group %s on %s: %s", group, stream, e
            )
    finally:
        await client.aclose()


async def stream_read_group(
    stream: str, group: str, consumer: str, count: int = 1, block: int = 5000
) -> list[tuple[str, dict]]:
    """Read messages from a consumer group. Returns list of (msg_id, fields)."""
    client = _get_redis_client()
    if not client:
        return []
    try:
        result = await client.xreadgroup(
            group, consumer, {stream: ">"}, count=count, block=block
        )
        if not result:
            return []
        # result format: [[stream_name, [(msg_id, fields), ...]]]
        return result[0][1]
    except Exception:
        logger.debug("Stream read failed for %s", stream, exc_info=True)
        return []
    finally:
        await client.aclose()


async def stream_ack(stream: str, group: str, *msg_ids: str) -> None:
    """Acknowledge messages in a consumer group."""
    client = _get_redis_client()
    if not client:
        return
    try:
        await client.xack(stream, group, *msg_ids)
    finally:
        await client.aclose()


async def stream_len(stream: str) -> int:
    """Get the length of a stream."""
    client = _get_redis_client()
    if not client:
        return 0
    try:
        return await client.xlen(stream)
    except Exception:
        return 0
    finally:
        await client.aclose()


async def delete_stream(stream: str) -> None:
    """Delete a Redis Stream entirely."""
    client = _get_redis_client()
    if not client:
        return
    try:
        await client.delete(stream)
    except Exception:
        logger.warning("Failed to delete stream %s", stream, exc_info=True)
    finally:
        await client.aclose()


async def write_batch_to_stream(
    stream: str, batch: list[dict], chunk_index: int
) -> str | None:
    """Serialize a batch of contacts and write to stream."""
    payload = json.dumps({"chunk_index": chunk_index, "contacts": batch}, default=str)
    return await stream_add(stream, {"data": payload})


async def write_sentinel(stream: str, total_batches: int) -> str | None:
    """Write a sentinel message marking end of input."""
    payload = json.dumps({"sentinel": True, "total_batches": total_batches})
    return await stream_add(stream, {"data": payload})
