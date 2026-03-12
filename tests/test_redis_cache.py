"""Test redis cache utility."""

import pytest
from unittest.mock import patch

from app.utils.redis_cache import cached_response, set_cached_response


@pytest.mark.asyncio
async def test_cached_response_returns_none_when_redis_unavailable():
    with patch("app.utils.redis_cache._get_redis", return_value=None):
        result = await cached_response("test:key")
        assert result is None


@pytest.mark.asyncio
async def test_set_cached_response_noop_when_redis_unavailable():
    with patch("app.utils.redis_cache._get_redis", return_value=None):
        # Should not raise
        await set_cached_response("test:key", {"data": "test"})
