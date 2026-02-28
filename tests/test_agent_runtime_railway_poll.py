"""Tests for Railway log polling Celery task."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_poll_[RAILWAY_TOKEN_REDACTED]():
    """Railway poll creates and dispatches event when error count >= threshold."""
    from app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED] import poll_[RAILWAY_TOKEN_REDACTED]

    log_lines = [
        "2026-02-28 INFO starting",
        "2026-02-28 ERROR OOM kill on worker",
        "2026-02-28 ERROR connection refused to DB",
        "2026-02-28 ERROR timeout on /api/v1/search",
        "2026-02-28 ERROR panic: nil pointer",
        "2026-02-28 ERROR unhandled exception in task",
        "2026-02-28 INFO recovery complete",
    ]

    mock_stream_add = AsyncMock(return_value="1-0")

    with (
        patch("app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED].stream_add", mock_stream_add),
        patch(
            "app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED]._fetch_recent_logs",
            return_value=log_lines,
        ),
    ):
        await poll_[RAILWAY_TOKEN_REDACTED]()

    mock_stream_add.assert_called_once()
    import json

    call_args = mock_stream_add.call_args
    assert call_args[0][0] == "warmpath:agent_events"
    event = json.loads(call_args[0][1]["event"])
    assert event["type"] == "incident"
    assert event["source"] == "railway"
    assert event["payload"]["error_count"] == 5


@pytest.mark.asyncio
async def test_poll_[RAILWAY_TOKEN_REDACTED]():
    """Railway poll does not dispatch when error count < threshold."""
    from app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED] import poll_[RAILWAY_TOKEN_REDACTED]

    log_lines = [
        "2026-02-28 INFO starting",
        "2026-02-28 ERROR one error only",
        "2026-02-28 INFO all good",
    ]

    mock_stream_add = AsyncMock(return_value="1-0")

    with (
        patch("app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED].stream_add", mock_stream_add),
        patch(
            "app.agent_runtime.events.[RAILWAY_TOKEN_REDACTED]._fetch_recent_logs",
            return_value=log_lines,
        ),
    ):
        await poll_[RAILWAY_TOKEN_REDACTED]()

    mock_stream_add.assert_not_called()
