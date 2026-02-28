"""Tests for the agent runtime event consumer."""

import pytest
from unittest.mock import AsyncMock, patch

from app.agent_runtime.cost_guard import BudgetStatus
from app.agent_runtime.events.ingestion import create_event
from app.agent_runtime.runner import process_event


def _make_event():
    return create_event(
        event_type="code_change",
        source="github",
        payload={"branch": "fix/typo", "commits": ["abc"]},
    )


def _mock_graph(event):
    mock = AsyncMock()
    mock.ainvoke.return_value = {
        "event": event,
        "routed_teams": ["engineering"],
        "priority": "medium",
        "findings": [{"title": "Test finding"}],
        "actions": [],
        "needs_human": False,
        "human_decision": "",
        "handoffs": [],
    }
    return mock


@pytest.mark.asyncio
async def test_process_event_runs_graph_and_returns_findings():
    """process_event invokes the compiled graph and returns state."""
    event = _make_event()
    mock_graph = _mock_graph(event)

    with patch("app.agent_runtime.runner._get_compiled_graph", return_value=mock_graph):
        result = await process_event(event)
        assert result["routed_teams"] == ["engineering"]
        assert len(result["findings"]) == 1
        mock_graph.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_process_event_skips_when_budget_exceeded():
    """process_event returns empty findings when daily budget is exceeded."""
    event = _make_event()
    mock_graph = _mock_graph(event)

    with (
        patch("app.agent_runtime.runner._get_compiled_graph", return_value=mock_graph),
        patch(
            "app.agent_runtime.runner._get_budget_status",
            return_value=BudgetStatus.EXCEEDED,
        ),
    ):
        result = await process_event(event)
        assert result["budget_exceeded"] is True
        assert result["findings"] == []
        mock_graph.ainvoke.assert_not_called()


@pytest.mark.asyncio
async def test_process_event_passes_budget_warning_in_config():
    """When budget is WARNING, budget_status is passed through config."""
    event = _make_event()
    mock_graph = _mock_graph(event)

    with (
        patch("app.agent_runtime.runner._get_compiled_graph", return_value=mock_graph),
        patch(
            "app.agent_runtime.runner._get_budget_status",
            return_value=BudgetStatus.WARNING,
        ),
    ):
        result = await process_event(event)
        assert len(result["findings"]) == 1
        # Verify budget_status was passed in config
        call_config = mock_graph.ainvoke.call_args[1]["config"]
        assert call_config["configurable"]["budget_status"] == "warning"


@pytest.mark.asyncio
async def test_run_consumer_loop_exits_when_runtime_disabled():
    """Consumer loop exits immediately when AGENT_RUNTIME_ENABLED=False."""
    from app.agent_runtime.runner import run_consumer_loop

    mock_settings = type("S", (), {"AGENT_RUNTIME_ENABLED": False})()
    with patch("app.config.settings", mock_settings):
        # Should return without connecting to Redis
        await run_consumer_loop()
        # If we get here without error, the guard worked
