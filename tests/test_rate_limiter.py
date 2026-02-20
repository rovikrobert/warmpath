"""Tests for Redis-based distributed rate limiter."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.rate_limiter import (
    _key,
    acqui[RESEND_KEY_REDACTED],
    get_queue_depth,
    init_limiter,
    release_slot,
)


class TestLocalFallback:
    """When Redis is unavailable, falls back to local asyncio.Semaphore."""

    @pytest.mark.asyncio
    async def test_acqui[RESEND_KEY_REDACTED](self):
        """Local semaphore works when Redis is unavailable."""
        with patch("app.utils.rate_limiter._get_redis_client", return_value=None):
            used_redis = await acqui[RESEND_KEY_REDACTED]("test_local", max_concurrent=2)
            assert used_redis is False
            await release_slot("test_local", used_redis=False)

    @pytest.mark.asyncio
    async def test_local_fallback_limits_concurrency(self):
        """Local semaphore enforces max_concurrent limit."""
        acquired = 0

        async def try_acquire():
            nonlocal acquired
            with patch("app.utils.rate_limiter._get_redis_client", return_value=None):
                await acqui[RESEND_KEY_REDACTED]("test_concurrency", max_concurrent=1, timeout=1)
                acquired += 1
                await asyncio.sleep(0.5)
                await release_slot("test_concurrency", used_redis=False)

        # First acquire should succeed, second should timeout
        with patch("app.utils.rate_limiter._get_redis_client", return_value=None):
            await acqui[RESEND_KEY_REDACTED]("test_concurrency", max_concurrent=1)

        with (
            pytest.raises((asyncio.TimeoutError, TimeoutError)),
            patch("app.utils.rate_limiter._get_redis_client", return_value=None),
        ):
            await acqui[RESEND_KEY_REDACTED]("test_concurrency", max_concurrent=1, timeout=0)

        # Release so other tests aren't blocked
        await release_slot("test_concurrency", used_redis=False)


class TestRedisLimiter:
    """Tests with mocked Redis client."""

    def _mock_redis(self):
        """Create a mock Redis client with list-based semaphore behavior."""
        client = AsyncMock()
        client.aclose = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_init_limiter_populates_tokens(self):
        """init_limiter creates tokens up to max_concurrent."""
        mock_client = self._mock_redis()
        mock_client.llen = AsyncMock(return_value=0)
        mock_pipeline = AsyncMock()
        mock_pipeline.lpush = lambda *args: None  # pipeline.lpush is sync (buffered)
        mock_pipeline.execute = AsyncMock()
        mock_client.pipeline = lambda: mock_pipeline

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            await init_limiter("test", max_concurrent=5)

        mock_pipeline.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_limiter_is_idempotent(self):
        """init_limiter doesn't add tokens if already at max."""
        mock_client = self._mock_redis()
        mock_client.llen = AsyncMock(return_value=5)

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            await init_limiter("test", max_concurrent=5)

        # Should not create a pipeline since no tokens needed
        mock_client.llen.assert_called_once()

    @pytest.mark.asyncio
    async def test_acqui[RESEND_KEY_REDACTED](self):
        """acqui[RESEND_KEY_REDACTED] uses BRPOP to take a token from the list."""
        mock_client = self._mock_redis()
        mock_client.llen = AsyncMock(return_value=5)
        mock_client.brpop = AsyncMock(return_value=(_key("test"), "1"))

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            used_redis = await acqui[RESEND_KEY_REDACTED]("test", max_concurrent=5)

        assert used_redis is True
        mock_client.brpop.assert_called_once()

    @pytest.mark.asyncio
    async def test_acqui[RESEND_KEY_REDACTED](self):
        """acqui[RESEND_KEY_REDACTED] raises TimeoutError when BRPOP returns None."""
        mock_client = self._mock_redis()
        mock_client.llen = AsyncMock(return_value=5)
        mock_client.brpop = AsyncMock(return_value=None)

        with (
            pytest.raises(TimeoutError, match="exhausted"),
            patch("app.utils.rate_limiter._get_redis_client", return_value=mock_client),
        ):
            await acqui[RESEND_KEY_REDACTED]("test", max_concurrent=5, timeout=1)

    @pytest.mark.asyncio
    async def test_release_slot_pushes_token_back(self):
        """release_slot uses LPUSH to return the token."""
        mock_client = self._mock_redis()

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            await release_slot("test", used_redis=True)

        mock_client.lpush.assert_called_once_with(_key("test"), "1")

    @pytest.mark.asyncio
    async def test_release_slot_local_fallback(self):
        """release_slot releases local semaphore when used_redis=False."""
        sem = asyncio.Semaphore(1)
        await sem.acquire()

        with patch("app.utils.rate_limiter._local_semaphores", {"test": sem}):
            await release_slot("test", used_redis=False)

        # Should be able to acquire again after release
        assert not sem.locked()

    @pytest.mark.asyncio
    async def test_acqui[RESEND_KEY_REDACTED](self):
        """If Redis fails during acquire, falls back to local semaphore."""
        mock_client = self._mock_redis()
        mock_client.llen = AsyncMock(side_effect=ConnectionError("Redis down"))

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            used_redis = await acqui[RESEND_KEY_REDACTED]("test_error", max_concurrent=2)

        assert used_redis is False


class TestQueueDepth:
    """Tests for queue depth monitoring."""

    @pytest.mark.asyncio
    async def test_returns_queue_length(self):
        """get_queue_depth returns Redis LLEN result."""
        mock_client = AsyncMock()
        mock_client.llen = AsyncMock(return_value=15)
        mock_client.aclose = AsyncMock()

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            depth = await get_queue_depth("celery")

        assert depth == 15

    @pytest.mark.asyncio
    async def test_returns_zero_when_redis_unavailable(self):
        """get_queue_depth returns 0 when Redis is down (safe default)."""
        with patch("app.utils.rate_limiter._get_redis_client", return_value=None):
            depth = await get_queue_depth()

        assert depth == 0

    @pytest.mark.asyncio
    async def test_returns_zero_on_redis_error(self):
        """get_queue_depth returns 0 on Redis connection error."""
        mock_client = AsyncMock()
        mock_client.llen = AsyncMock(side_effect=ConnectionError("Redis down"))
        mock_client.aclose = AsyncMock()

        with patch(
            "app.utils.rate_limiter._get_redis_client", return_value=mock_client
        ):
            depth = await get_queue_depth()

        assert depth == 0
