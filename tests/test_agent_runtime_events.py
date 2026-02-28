"""Tests for event ingestion and deduplication."""

from app.agent_runtime.events.ingestion import create_event, compute_dedup_key


def test_create_event_builds_event_with_timestamp():
    """create_event produces a well-formed Event dict."""
    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "main", "commits": ["abc123"]},
    )
    assert event["type"] == "code_change"
    assert event["source"] == "github"
    assert event["payload"]["branch"] == "main"
    assert "timestamp" in event
    assert "dedup_key" in event


def test_dedup_key_is_stable_for_same_input():
    """Same type + payload_key produces same SHA-256 hash."""
    key1 = compute_dedup_key("code_change", "abc123")
    key2 = compute_dedup_key("code_change", "abc123")
    assert key1 == key2
    assert len(key1) == 64  # SHA-256 hex


def test_dedup_key_differs_for_different_input():
    """Different inputs produce different hashes."""
    key1 = compute_dedup_key("code_change", "abc123")
    key2 = compute_dedup_key("incident", "abc123")
    assert key1 != key2
