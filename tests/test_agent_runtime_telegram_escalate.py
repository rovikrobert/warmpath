"""Tests for Telegram escalation node."""

import pytest
from unittest.mock import patch

from app.agent_runtime.nodes.telegram_escalate import (
    format_escalation_message,
    send_escalation,
    _escalation_timestamps,
)


def test_format_escalation_message_includes_event_and_findings():
    msg = format_escalation_message(
        event_type="incident",
        priority="critical",
        findings_count=3,
        summary="Auth service returning 500s for 15 minutes",
    )
    assert "incident" in msg.lower()
    assert "critical" in msg.lower()
    assert "3" in msg
    assert "Auth service" in msg


def test_format_escalation_message_includes_action_prompt():
    msg = format_escalation_message(
        event_type="code_change",
        priority="high",
        findings_count=1,
        summary="Security vulnerability in auth middleware",
    )
    assert "approve" in msg.lower() or "reply" in msg.lower()


@pytest.mark.asyncio
async def test_send_escalation_returns_false_when_not_configured():
    """Returns False when Telegram env vars are not set."""
    _escalation_timestamps.clear()
    with patch.dict("os.environ", {}, clear=True):
        result = await send_escalation("incident", "high", 1, "test")
        assert result is False


@pytest.mark.asyncio
async def test_send_escalation_rate_limited_after_burst():
    """Escalation is rate-limited: max 5 per minute."""
    import time

    _escalation_timestamps.clear()
    # Simulate 5 recent timestamps
    now = time.monotonic()
    for i in range(5):
        _escalation_timestamps.append(now - i)

    # 6th should be rate-limited (no env vars needed, it short-circuits)
    result = await send_escalation("incident", "high", 1, "Error")
    assert result is False
