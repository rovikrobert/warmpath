# tests/test_agent_runtime_cos_route.py
"""Tests for CoS routing node — event to team assignment."""

from app.agent_runtime.nodes.cos_route import cos_route
from app.agent_runtime.state import WarmPathState


def _make_state(**overrides) -> WarmPathState:
    base: WarmPathState = {
        "event": {},
        "routed_teams": [],
        "priority": "medium",
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }
    base.update(overrides)
    return base


def test_incident_routes_to_engineering():
    """Production incidents always route to engineering team."""
    state = _make_state(
        event={"type": "incident", "source": "railway", "payload": {"error_count": 10}},
        priority="critical",
    )
    result = cos_route(state)
    assert "engineering" in result["routed_teams"]


def test_code_change_routes_to_engineering():
    """Code changes route to engineering for review."""
    state = _make_state(
        event={
            "type": "code_change",
            "source": "github",
            "payload": {"branch": "fix/auth"},
        },
    )
    result = cos_route(state)
    assert "engineering" in result["routed_teams"]


def test_external_signal_routes_to_gtm():
    """Competitor signals route to GTM team."""
    state = _make_state(
        event={
            "type": "external_signal",
            "source": "intelligence",
            "payload": {"signal_type": "competitor_update"},
        },
    )
    result = cos_route(state)
    assert "gtm" in result["routed_teams"]


def test_critical_incident_routes_to_multiple_teams():
    """Critical incidents also loop in ops (user impact check)."""
    state = _make_state(
        event={"type": "incident", "source": "railway", "payload": {"error_count": 50}},
        priority="critical",
    )
    result = cos_route(state)
    assert "engineering" in result["routed_teams"]
    assert "ops" in result["routed_teams"]
