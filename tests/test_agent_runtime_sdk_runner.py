"""Tests for the Claude Agent SDK session runner."""

from unittest.mock import patch

import pytest

from app.agent_runtime.sdk.runner import run_sdk_session


def _make_assistant_msg(text: str):
    """Create a mock AssistantMessage with a TextBlock."""
    from claude_code_sdk.types import AssistantMessage, TextBlock

    return AssistantMessage(
        content=[TextBlock(text=text)],
        model="claude-sonnet-4-20250514",
    )


def _make_result_msg(cost: float = 0.02, turns: int = 3):
    """Create a mock ResultMessage."""
    from claude_code_sdk.types import ResultMessage

    return ResultMessage(
        subtype="success",
        duration_ms=5000,
        duration_api_ms=4000,
        is_error=False,
        num_turns=turns,
        session_id="test-session",
        total_cost_usd=cost,
        usage=None,
        result="Analysis complete",
    )


async def _mock_query_gen(*_args, **_kwargs):
    """Mock query() that yields assistant + result messages."""
    yield _make_assistant_msg("## Finding: Unused import\n**Validated:** yes")
    yield _make_assistant_msg("## Finding: Missing test\n**Validated:** yes")
    yield _make_result_msg(cost=0.03, turns=2)


@pytest.mark.asyncio
async def test_run_sdk_session_collects_messages_and_cost():
    """SDK runner collects assistant messages and extracts cost from result."""
    with patch("app.agent_runtime.sdk.runner.query", side_effect=_mock_query_gen):
        result = await run_sdk_session(
            prompt="Analyze these findings",
            system_prompt="You are a code reviewer",
            max_turns=5,
        )

    assert len(result["messages"]) == 2
    assert result["messages"][0]["role"] == "assistant"
    assert "Unused import" in result["messages"][0]["content"]
    assert result["cost_usd"] == 0.03
    assert result["num_turns"] == 2
    assert result["model"] == "claude-sonnet-4-20250514"


async def _mock_query_empty(*_args, **_kwargs):
    """Mock query() that yields only a result (no assistant messages)."""
    yield _make_result_msg(cost=0.0, turns=0)


@pytest.mark.asyncio
async def test_run_sdk_session_handles_empty_response():
    """SDK runner handles sessions with no assistant messages."""
    with patch("app.agent_runtime.sdk.runner.query", side_effect=_mock_query_empty):
        result = await run_sdk_session(
            prompt="Nothing to analyze",
            system_prompt="You are a reviewer",
        )

    assert result["messages"] == []
    assert result["cost_usd"] == 0.0
    assert result["num_turns"] == 0
