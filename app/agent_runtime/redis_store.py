"""Redis-backed storage for event dedup, trust levels, and cost tracking."""

from __futu[RESEND_KEY_REDACTED] import annotations

from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.agent_runtime.trust import TrustLevel

PREFIX = "agentrt"


class AgentRuntimeRedis:
    """Thin async wrapper for agent runtime Redis operations."""

    def __init__(self, redis: aioredis.Redis | None = None, redis_url: str = ""):
        self._redis = redis
        self._redis_url = redis_url

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def is_duplicate(self, dedup_key: str, cooldown_seconds: int) -> bool:
        """Check if this event was seen within the cooldown window."""
        r = await self._get_redis()
        key = f"{PREFIX}:dedup:{dedup_key}"
        exists = await r.exists(key)
        if exists:
            return True
        await r.set(key, "1", ex=cooldown_seconds)
        return False

    async def get_trust_level(self, agent_name: str) -> TrustLevel:
        """Get agent's current trust level (default: OBSERVER)."""
        r = await self._get_redis()
        val = await r.get(f"{PREFIX}:trust:{agent_name}")
        if val is None:
            return TrustLevel.OBSERVER
        return TrustLevel(int(val))

    async def set_trust_level(self, agent_name: str, level: TrustLevel) -> None:
        """Set agent's trust level."""
        r = await self._get_redis()
        await r.set(f"{PREFIX}:trust:{agent_name}", int(level))

    async def record_spend(self, usd: float) -> None:
        """Add to today's spend counter."""
        r = await self._get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{PREFIX}:spend:{today}"
        await r.incrbyfloat(key, usd)
        await r.expire(key, 86400 * 2)

    async def get_daily_spend(self) -> float:
        """Get today's cumulative spend in USD."""
        r = await self._get_redis()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        val = await r.get(f"{PREFIX}:spend:{today}")
        return float(val) if val else 0.0
