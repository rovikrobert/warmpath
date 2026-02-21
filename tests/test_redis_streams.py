"""Tests for Redis Streams helpers — local fallback (no real Redis in tests)."""

import pytest
from unittest.mock import AsyncMock, patch


class TestRedisStreamHelpers:
    @pytest.mark.asyncio
    async def test_stream_add_returns_message_id(self):
        from app.utils.redis_streams import stream_add

        mock_client = AsyncMock()
        mock_client.xadd = AsyncMock(return_value="1234-0")
        mock_client.aclose = AsyncMock()
        with patch(
            "app.utils.redis_streams._get_redis_client", return_value=mock_client
        ):
            msg_id = await stream_add("test:stream", {"data": '{"test": 1}'})
            assert msg_id == "1234-0"
            mock_client.xadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_read_group_returns_messages(self):
        from app.utils.redis_streams import stream_read_group

        mock_client = AsyncMock()
        mock_client.xreadgroup = AsyncMock(
            return_value=[["test:stream", [["1234-0", {"data": '{"test": 1}'}]]]]
        )
        mock_client.aclose = AsyncMock()
        with patch(
            "app.utils.redis_streams._get_redis_client", return_value=mock_client
        ):
            messages = await stream_read_group(
                "test:stream", "group", "consumer", count=1
            )
            assert len(messages) == 1
            assert messages[0][0] == "1234-0"

    @pytest.mark.asyncio
    async def test_create_consumer_group_is_idempotent(self):
        from app.utils.redis_streams import ensu[RESEND_KEY_REDACTED]

        mock_client = AsyncMock()
        mock_client.xgroup_create = AsyncMock()
        mock_client.aclose = AsyncMock()
        with patch(
            "app.utils.redis_streams._get_redis_client", return_value=mock_client
        ):
            await ensu[RESEND_KEY_REDACTED]("test:stream", "group")
            mock_client.xgroup_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_stream(self):
        from app.utils.redis_streams import delete_stream

        mock_client = AsyncMock()
        mock_client.delete = AsyncMock()
        mock_client.aclose = AsyncMock()
        with patch(
            "app.utils.redis_streams._get_redis_client", return_value=mock_client
        ):
            await delete_stream("test:stream")
            mock_client.delete.assert_called_once_with("test:stream")

    @pytest.mark.asyncio
    async def test_stream_add_returns_none_when_no_redis(self):
        from app.utils.redis_streams import stream_add

        with patch("app.utils.redis_streams._get_redis_client", return_value=None):
            result = await stream_add("test:stream", {"data": "test"})
            assert result is None

    @pytest.mark.asyncio
    async def test_stream_key_helpers(self):
        from app.utils.redis_streams import parsed_stream_key, cleaned_stream_key

        assert parsed_stream_key("abc-123") == "csv:parsed:abc-123"
        assert cleaned_stream_key("abc-123") == "csv:cleaned:abc-123"

    @pytest.mark.asyncio
    async def test_write_batch_to_stream(self):
        from app.utils.redis_streams import write_batch_to_stream
        import json

        mock_client = AsyncMock()
        mock_client.xadd = AsyncMock(return_value="1234-0")
        mock_client.aclose = AsyncMock()
        with patch(
            "app.utils.redis_streams._get_redis_client", return_value=mock_client
        ):
            result = await write_batch_to_stream("test:stream", [{"name": "Alice"}], 0)
            assert result == "1234-0"
            # Verify the payload structure
            call_args = mock_client.xadd.call_args
            payload = json.loads(call_args[0][1]["data"])
            assert payload["chunk_index"] == 0
            assert payload["contacts"] == [{"name": "Alice"}]
