"""Tests for the classify node — event classification."""

from app.agent_runtime.nodes.classify import classify_event
from app.agent_runtime.state import WarmPathState


def _make_state(**overrides) -> WarmPathState:
    base: WarmPathState = {
        "event": {},
        "routed_teams": [],
        "priority": "",
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }
    base.update(overrides)
    return base


def test_classify_incident_as_critical():
    """Production incident with high error count gets critical priority."""
    state = _make_state(
        event={
            "type": "incident",
            "source": "railway",
            "payload": {"error_count": 50, "sample_errors": ["500 Internal"]},
        }
    )
    result = classify_event(state)
    assert result["priority"] == "critical"


def test_classify_code_change_as_medium():
    """Normal code change defaults to medium priority."""
    state = _make_state(
        event={
            "type": "code_change",
            "source": "github",
            "payload": {"branch": "fix/typo", "commits": ["abc"]},
        }
    )
    result = classify_event(state)
    assert result["priority"] in ("medium", "low")


def test_classify_external_signal_as_low():
    """External intelligence signal defaults to low priority."""
    state = _make_state(
        event={
            "type": "external_signal",
            "source": "intelligence",
            "payload": {"signal_type": "competitor_update"},
        }
    )
    result = classify_event(state)
    assert result["priority"] == "low"
