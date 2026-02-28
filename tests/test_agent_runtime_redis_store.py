"""Tests for Redis-backed dedup and trust storage. Uses fakeredis."""

import pytest
import fakeredis.aioredis

from app.agent_runtime.redis_store import AgentRuntimeRedis
from app.agent_runtime.trust import TrustLevel


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def store(fake_redis):
    return AgentRuntimeRedis(redis=fake_redis)


@pytest.mark.asyncio
async def test_is_duplicate_returns_false_first_time(store):
    """First event with a given dedup key is not a duplicate."""
    is_dup = await store.is_duplicate("key123", cooldown_seconds=900)
    assert is_dup is False


@pytest.mark.asyncio
async def test_is_duplicate_returns_true_within_cooldown(store):
    """Same dedup key within cooldown is flagged as duplicate."""
    await store.is_duplicate("key123", cooldown_seconds=900)
    is_dup = await store.is_duplicate("key123", cooldown_seconds=900)
    assert is_dup is True


@pytest.mark.asyncio
async def test_get_trust_level_defaults_to_observer(store):
    """Unknown agents default to trust level 0 (observer)."""
    level = await store.get_trust_level("unknown_agent")
    assert level == TrustLevel.OBSERVER


@pytest.mark.asyncio
async def test_set_and_get_trust_level(store):
    """Trust level can be set and retrieved."""
    await store.set_trust_level("engineering", TrustLevel.CONTRIBUTOR)
    level = await store.get_trust_level("engineering")
    assert level == TrustLevel.CONTRIBUTOR


@pytest.mark.asyncio
async def test_record_spend_and_get_daily_spend(store):
    """Daily spend accumulates and is retrievable."""
    await store.record_spend(0.50)
    await store.record_spend(0.25)
    total = await store.get_daily_spend()
    assert abs(total - 0.75) < 0.01
