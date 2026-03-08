"""Test cto:events stream publishing and reading."""

from agents.shared.event_stream import format_event, parse_event


def test_format_event():
    event = format_event(
        team="engineering",
        agent="deps_manager",
        finding_id="dep-1",
        tier="auto_do",
        action="auto_fixed",
        detail="Bumped requests 2.31.0 -> 2.32.0",
    )
    assert event["team"] == "engineering"
    assert event["agent"] == "deps_manager"
    assert "timestamp" in event


def test_parse_event():
    raw = {
        b"team": b"engineering",
        b"agent": b"deps_manager",
        b"action": b"auto_fixed",
        b"detail": b"Bumped requests",
        b"timestamp": b"2026-03-08T10:00:00Z",
    }
    parsed = parse_event(raw)
    assert parsed["team"] == "engineering"
    assert parsed["action"] == "auto_fixed"


def test_format_event_defaults():
    event = format_event(team="data", agent="pipeline")
    assert event["team"] == "data"
    assert event["finding_id"] == ""
    assert event["tier"] == ""
