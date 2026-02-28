"""Tests for Telegram escalation node."""

from app.agent_runtime.nodes.telegram_escalate import format_escalation_message


def test_format_escalation_message_includes_event_and_findings():
    msg = format_escalation_message(
        event_type="incident", priority="critical", findings_count=3,
        summary="Auth service returning 500s for 15 minutes",
    )
    assert "incident" in msg.lower()
    assert "critical" in msg.lower()
    assert "3" in msg
    assert "Auth service" in msg


def test_format_escalation_message_includes_action_prompt():
    msg = format_escalation_message(
        event_type="code_change", priority="high", findings_count=1,
        summary="Security vulnerability in auth middleware",
    )
    assert "approve" in msg.lower() or "reply" in msg.lower()
