"""Tests for scheduled scan dispatch and routing."""

from unittest.mock import AsyncMock, patch

from app.agent_runtime.nodes.classify import classify_event
from app.agent_runtime.nodes.cos_route import cos_route
from app.agent_runtime.state import WarmPathState


def _make_state(event_type: str, **payload_overrides) -> WarmPathState:
    payload = {"cadence": "daily", **payload_overrides}
    return {
        "event": {"type": event_type, "source": "celery_beat", "payload": payload},
        "routed_teams": [],
        "priority": "",
        "trust_level": 1,
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }


def test_scheduled_scan_classified_as_low_priority():
    """Scheduled scans get low priority to avoid unnecessary escalation."""
    state = _make_state("scheduled_scan")
    result = classify_event(state)
    assert result["priority"] == "low"


def test_daily_scan_routes_to_all_six_teams():
    """Daily scan dispatches to all 6 teams."""
    state = _make_state("scheduled_scan", cadence="daily")
    state["priority"] = "low"
    result = cos_route(state)
    assert sorted(result["routed_teams"]) == sorted(
        ["engineering", "data", "product", "ops", "gtm", "finance"]
    )


def test_weekly_scan_routes_to_all_six_teams():
    """Weekly scan dispatches to all 6 teams."""
    state = _make_state("scheduled_scan", cadence="weekly")
    state["priority"] = "low"
    result = cos_route(state)
    assert sorted(result["routed_teams"]) == sorted(
        ["engineering", "data", "product", "ops", "gtm", "finance"]
    )


def test_dispatch_scheduled_scan_skips_when_runtime_disabled():
    """Task exits early when AGENT_RUNTIME_ENABLED=False."""
    from app.tasks.agent_runtime_tasks import dispatch_scheduled_scan

    with patch("app.config.settings.AGENT_RUNTIME_ENABLED", False):
        # Should not raise or attempt Redis connection
        dispatch_scheduled_scan("daily")


def test_dispatch_scheduled_scan_sends_event_to_stream():
    """Task dispatches event to Redis Stream when runtime enabled."""
    mock_stream_add = AsyncMock(return_value="1-0")
    with (
        patch("app.config.settings.AGENT_RUNTIME_ENABLED", True),
        patch(
            "app.utils.redis_streams.stream_add",
            mock_stream_add,
        ),
    ):
        from app.tasks.agent_runtime_tasks import dispatch_scheduled_scan

        dispatch_scheduled_scan("weekly")

        mock_stream_add.assert_called_once()
        call_args = mock_stream_add.call_args[0]
        assert call_args[0] == "warmpath:agent_events"
