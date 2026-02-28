"""Tests for agent runtime state schema."""

from app.agent_runtime.state import WarmPathState, EventType, Priority


def test_warmpath_state_has_required_keys():
    """WarmPathState TypedDict contains all routing and audit fields."""
    annotations = WarmPathState.__annotations__
    assert "event" in annotations
    assert "routed_teams" in annotations
    assert "priority" in annotations
    assert "findings" in annotations
    assert "actions" in annotations
    assert "needs_human" in annotations
    assert "human_decision" in annotations
    assert "handoffs" in annotations


def test_event_type_enum_has_four_sources():
    """EventType covers all four trigger sources."""
    assert EventType.CODE_CHANGE.value == "code_change"
    assert EventType.INCIDENT.value == "incident"
    assert EventType.EXTERNAL_SIGNAL.value == "external_signal"
    assert EventType.AGENT_FINDING.value == "agent_finding"


def test_priority_enum_has_four_levels():
    """Priority enum has critical/high/medium/low."""
    assert Priority.CRITICAL.value == "critical"
    assert Priority.HIGH.value == "high"
    assert Priority.MEDIUM.value == "medium"
    assert Priority.LOW.value == "low"
