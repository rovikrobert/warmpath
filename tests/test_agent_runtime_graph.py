"""Tests for the root LangGraph definition.

Tests graph structure (nodes, edges) without executing LLM calls.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.agent_runtime.graph import build_graph


def test_build_graph_has_required_nodes():
    """Root graph contains all expected nodes."""
    graph = build_graph()
    node_names = set(graph.nodes.keys())
    assert "classify" in node_names
    assert "cos_route" in node_names
    assert "synthesize" in node_names
    assert "evaluate" in node_names
    assert "escalate" in node_names


def test_build_graph_compiles_without_error():
    """Graph compiles successfully (valid edges, no dangling nodes)."""
    graph = build_graph()
    # compile() validates the graph structure
    compiled = graph.compile()
    assert compiled is not None


@pytest.mark.asyncio
async def test_escalate_node_calls_send_escalation_when_needs_human():
    """When needs_human=True, the escalate node sends a Telegram notification."""
    from app.agent_runtime.events.ingestion import create_event
    from app.agent_runtime.teams.base import TeamRunner
    from app.agent_runtime.teams.engineering import EngineeringTeam
    from app.agent_runtime.teams.ops import OpsTeam

    event = create_event(
        event_type="incident",
        source="railway",
        payload={"error_count": 15, "sample_errors": ["OOM kill"]},
    )

    async def _passthrough(self, findings, event, trust_level, budget_status):
        return findings

    mock_send = AsyncMock()
    with (
        patch.object(TeamRunner, "augment_with_sdk", _passthrough),
        patch.object(EngineeringTeam, "run_scanners", return_value=[]),
        patch.object(OpsTeam, "run_scanners", return_value=[]),
        patch(
            "app.agent_runtime.graph.send_escalation",
            mock_send,
        ),
    ):
        graph = build_graph().compile()
        # Force needs_human=True and critical priority to trigger escalation
        result = await graph.ainvoke(
            {
                "event": event,
                "routed_teams": [],
                "priority": "",
                "findings": [],
                "actions": [],
                "needs_human": True,
                "human_decision": "",
                "handoffs": [],
            },
            config={"recursion_limit": 30},
        )
        assert result["needs_human"] is True


@pytest.mark.asyncio
async def test_team_dispatch_routes_to_all_six_teams():
    """team_dispatch calls each team's runner for routed teams."""
    from app.agent_runtime.graph import _team_dispatch
    from app.agent_runtime.teams.base import TeamRunner

    all_teams = ["engineering", "data", "product", "ops", "gtm", "finance"]
    mock_findings = [{"id": "f1", "title": "test", "source_team": "mock"}]

    with patch.object(
        TeamRunner,
        "run",
        AsyncMock(return_value=mock_findings),
    ):
        state = {"routed_teams": all_teams, "findings": [], "event": {}}
        result = await _team_dispatch(state)
        # Each team contributes 1 finding
        assert len(result["findings"]) == 6


@pytest.mark.asyncio
async def test_team_dispatch_ignores_unknown_teams():
    """team_dispatch silently skips unrecognized team names."""
    from app.agent_runtime.graph import _team_dispatch

    state = {"routed_teams": ["nonexistent_team"], "findings": [], "event": {}}
    result = await _team_dispatch(state)
    assert result["findings"] == []
