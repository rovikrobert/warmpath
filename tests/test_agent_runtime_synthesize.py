"""Tests for synthesize, evaluate, and escalate nodes."""

from app.agent_runtime.nodes.synthesize import synthesize_findings
from app.agent_runtime.nodes.evaluate import evaluate_handoffs
from app.agent_runtime.nodes.escalate import should_escalate
from app.agent_runtime.state import WarmPathState


def _make_state(**overrides) -> WarmPathState:
    base: WarmPathState = {
        "event": {"type": "incident", "source": "railway", "payload": {}},
        "routed_teams": ["engineering"],
        "priority": "medium",
        "findings": [],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }
    base.update(overrides)
    return base


def test_synthesize_detects_cross_team_handoff():
    state = _make_state(
        findings=[
            {
                "severity": "high",
                "category": "security",
                "title": "Auth bypass found",
                "cross_team_request": {"to_team": "ops", "reason": "Check user impact"},
            },
        ]
    )
    result = synthesize_findings(state)
    assert len(result["handoffs"]) == 1
    assert result["handoffs"][0]["to_team"] == "ops"


def test_synthesize_no_handoff_when_no_cross_team():
    state = _make_state(
        findings=[
            {"severity": "low", "category": "lint", "title": "Unused import"},
        ]
    )
    result = synthesize_findings(state)
    assert len(result["handoffs"]) == 0


def test_evaluate_returns_done_when_no_handoffs():
    state = _make_state(handoffs=[])
    result = evaluate_handoffs(state)
    assert result == "done"


def test_evaluate_returns_route_when_handoffs_pending():
    state = _make_state(
        handoffs=[
            {"from_team": "engineering", "to_team": "ops", "reason": "Check impact"},
        ]
    )
    result = evaluate_handoffs(state)
    assert result == "route"


def test_should_escalate_on_critical_with_no_contributor():
    assert should_escalate(priority="critical", max_trust_level=0) is True


def test_should_not_escalate_on_low_priority():
    assert should_escalate(priority="low", max_trust_level=0) is False
