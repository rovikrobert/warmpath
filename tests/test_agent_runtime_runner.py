"""Tests for the agent runtime event consumer."""

import pytest
from unittest.mock import AsyncMock, patch

from app.agent_runtime.runner import process_event
from app.agent_runtime.events.ingestion import create_event


@pytest.mark.asyncio
async def test_process_event_runs_graph_and_returns_findings():
    """process_event invokes the compiled graph and returns state."""
    event = create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "fix/typo", "commits": ["abc"]},
    )

    mock_graph = AsyncMock()
    mock_graph.ainvoke.return_value = {
        "event": event,
        "routed_teams": ["engineering"],
        "priority": "medium",
        "findings": [{"title": "Test finding"}],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }

    with patch("app.agent_runtime.runner._get_compiled_graph", return_value=mock_graph):
        result = await process_event(event)
        assert result["routed_teams"] == ["engineering"]
        assert len(result["findings"]) == 1
        mock_graph.ainvoke.assert_called_once()
