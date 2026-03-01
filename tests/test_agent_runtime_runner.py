"""Tests for the agent runtime event consumer."""

import json

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
        "trust_level": 1,
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
async def test_process_event_includes_trust_level_in_config():
    """process_event passes trust_level in both initial state and config."""
    event = _make_event()
    mock_graph = _mock_graph(event)

    with patch("app.agent_runtime.runner._get_compiled_graph", return_value=mock_graph):
        await process_event(event)
        call_args = mock_graph.ainvoke.call_args
        initial_state = call_args[0][0]
        config = call_args[1]["config"]
        assert initial_state["trust_level"] == 1
        assert config["configurable"]["trust_level"] == 1


@pytest.mark.asyncio
async def test_run_consumer_loop_exits_when_runtime_disabled():
    """Consumer loop exits immediately when AGENT_RUNTIME_ENABLED=False."""
    from app.agent_runtime.runner import run_consumer_loop

    mock_settings = type("S", (), {"AGENT_RUNTIME_ENABLED": False})()
    with patch("app.config.settings", mock_settings):
        # Should return without connecting to Redis
        await run_consumer_loop()
        # If we get here without error, the guard worked


@pytest.mark.asyncio
async def test_consumer_loop_skips_duplicate_events_and_acks():
    """Duplicate events are skipped but still ACK'd in the stream."""
    import asyncio

    from app.agent_runtime.runner import run_consumer_loop

    event = _make_event()
    event_json = json.dumps(event)

    # Mock Redis connection that returns one message then raises CancelledError
    mock_redis = AsyncMock()
    mock_redis.xgroup_create = AsyncMock()
    mock_redis.xreadgroup = AsyncMock(
        side_effect=[
            [("warmpath:agent_events", [("1-0", {"event": event_json})])],
            asyncio.CancelledError(),
        ]
    )
    mock_redis.xack = AsyncMock()
    mock_redis.aclose = AsyncMock()

    mock_settings = type(
        "S",
        (),
        {
            "AGENT_RUNTIME_ENABLED": True,
            "REDIS_URL": "redis://localhost:6379/0",
            "AGENT_RUNTIME_EVENT_COOLDOWN_SECONDS": 900,
        },
    )()

    mock_is_duplicate = AsyncMock(return_value=True)

    with (
        patch("app.config.settings", mock_settings),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch(
            "app.agent_runtime.runner.AgentRuntimeRedis.is_duplicate",
            mock_is_duplicate,
        ),
        patch("app.agent_runtime.runner.process_event") as mock_process,
    ):
        await run_consumer_loop()

        # Duplicate detected — process_event never called
        mock_process.assert_not_called()
        # Message was still ACK'd
        mock_redis.xack.assert_called_once()


@pytest.mark.asyncio
async def test_run_cos_brief_calls_run_daily_for_daily_cadence():
    """_run_cos_brief calls CoS run_daily for daily scans."""
    from app.agent_runtime.runner import _run_cos_brief

    with patch(
        "agents.chief_of_staff.cos_agent.run_daily", return_value="# Daily Brief"
    ) as mock_daily:
        await _run_cos_brief("daily")
    mock_daily.assert_called_once()


@pytest.mark.asyncio
async def test_run_cos_brief_calls_run_weekly_for_weekly_cadence():
    """_run_cos_brief calls CoS run_weekly for weekly scans."""
    from app.agent_runtime.runner import _run_cos_brief

    with patch(
        "agents.chief_of_staff.cos_agent.run_weekly", return_value="# Weekly Brief"
    ) as mock_weekly:
        await _run_cos_brief("weekly")
    mock_weekly.assert_called_once()


@pytest.mark.asyncio
async def test_run_cos_brief_handles_failure_gracefully():
    """_run_cos_brief logs exception but does not raise."""
    from app.agent_runtime.runner import _run_cos_brief

    with patch(
        "agents.chief_of_staff.cos_agent.run_daily",
        side_effect=Exception("Notion down"),
    ):
        # Should not raise
        await _run_cos_brief("daily")


@pytest.mark.asyncio
async def test_consumer_loop_calls_cos_brief_after_scheduled_scan():
    """After processing a scheduled_scan event, consumer calls _run_cos_brief."""
    import asyncio

    from app.agent_runtime.runner import run_consumer_loop

    event = create_event(
        event_type="scheduled_scan",
        source="celery_beat",
        payload={"cadence": "daily"},
        payload_key="scheduled_daily",
    )
    event_json = json.dumps(event)

    mock_redis = AsyncMock()
    mock_redis.xgroup_create = AsyncMock()
    mock_redis.xreadgroup = AsyncMock(
        side_effect=[
            [("warmpath:agent_events", [("1-0", {"event": event_json})])],
            asyncio.CancelledError(),
        ]
    )
    mock_redis.xack = AsyncMock()
    mock_redis.aclose = AsyncMock()

    mock_settings = type(
        "S",
        (),
        {
            "AGENT_RUNTIME_ENABLED": True,
            "REDIS_URL": "redis://localhost:6379/0",
            "AGENT_RUNTIME_EVENT_COOLDOWN_SECONDS": 900,
        },
    )()

    mock_process = AsyncMock(
        return_value={"findings": [], "actions": [], "routed_teams": ["engineering"]}
    )

    with (
        patch("app.config.settings", mock_settings),
        patch("redis.asyncio.from_url", return_value=mock_redis),
        patch(
            "app.agent_runtime.runner.AgentRuntimeRedis.is_duplicate",
            AsyncMock(return_value=False),
        ),
        patch("app.agent_runtime.runner.process_event", mock_process),
        patch("app.agent_runtime.runner._run_cos_brief") as mock_cos,
    ):
        await run_consumer_loop()

    mock_process.assert_called_once()
    mock_cos.assert_called_once_with("daily")
