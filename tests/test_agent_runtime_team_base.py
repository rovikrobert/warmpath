"""Tests for TeamRunner base class with SDK augmentation."""

from unittest.mock import AsyncMock, patch

import pytest

from agents.shared.report import AgentReport, Finding
from app.agent_runtime.cost_guard import BudgetStatus
from app.agent_runtime.teams.base import TeamRunner
from app.agent_runtime.trust import TrustLevel


class _TestTeam(TeamRunner):
    team_name = "test_team"
    scanner_modules = {"scanner_a": "fake.module.a"}


def _mock_report():
    return AgentReport(
        agent="scanner_a",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="test",
                title="Test finding",
                detail="A test finding",
                file="app/test.py",
                line=1,
                recommendation="Fix it",
                effort_hours=0.5,
            )
        ],
    )


def test_run_scanners_returns_findings_with_source_team():
    """TeamRunner.run_scanners tags findings with team_name."""
    team = _TestTeam()
    with patch.object(team, "_run_scanner", return_value=_mock_report()):
        findings = team.run_scanners()
        assert len(findings) == 1
        assert findings[0]["source_team"] == "test_team"
        assert findings[0]["title"] == "Test finding"


def test_run_scanners_handles_failure():
    """TeamRunner.run_scanners catches exceptions and records error finding."""
    team = _TestTeam()
    with patch.object(team, "_run_scanner", side_effect=Exception("boom")):
        findings = team.run_scanners()
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "boom" in findings[0]["title"]


@pytest.mark.asyncio
async def test_augment_skipped_when_trust_below_recommender():
    """SDK augmentation is skipped when trust level < RECOMMENDER."""
    team = _TestTeam()
    original = [{"title": "Test", "severity": "low"}]
    result = await team.augment_with_sdk(
        original,
        event={"type": "test"},
        trust_level=TrustLevel.OBSERVER,
        budget_status=BudgetStatus.OK,
    )
    assert result is original  # returned unchanged


@pytest.mark.asyncio
async def test_augment_skipped_when_budget_exceeded():
    """SDK augmentation is skipped when budget is exceeded."""
    team = _TestTeam()
    original = [{"title": "Test", "severity": "low"}]
    result = await team.augment_with_sdk(
        original,
        event={"type": "test"},
        trust_level=TrustLevel.RECOMMENDER,
        budget_status=BudgetStatus.EXCEEDED,
    )
    assert result is original


@pytest.mark.asyncio
async def test_augment_calls_sdk_and_merges_findings():
    """SDK augmentation runs session and merges results into findings."""
    team = _TestTeam()
    scanner_findings = [{"title": "Test finding", "severity": "medium"}]

    sdk_output = {
        "messages": [
            {
                "role": "assistant",
                "content": (
                    "## Finding: Test finding\n"
                    "**Validated:** yes\n"
                    "**Adjusted Severity:** high\n"
                    "**Root Cause:** Missing validation\n"
                    "**Proposed Fix:** Add input check\n"
                    "**Cross-Team Impact:** None\n"
                ),
            }
        ],
        "model": "claude-sonnet-4-20250514",
        "cost_usd": 0.01,
        "num_turns": 1,
    }

    with patch(
        "app.agent_runtime.sdk.runner.run_sdk_session",
        AsyncMock(return_value=sdk_output),
    ):
        result = await team.augment_with_sdk(
            scanner_findings,
            event={"type": "code_change", "source": "github"},
            trust_level=TrustLevel.RECOMMENDER,
            budget_status=BudgetStatus.OK,
        )

    assert len(result) == 1
    assert result[0]["severity"] == "high"  # upgraded by SDK
    assert result[0]["root_cause"] == "Missing validation"
    assert result[0]["sdk_augmented"] is True


@pytest.mark.asyncio
async def test_augment_records_spend_after_sdk_session():
    """SDK augmentation records cost via redis_store.record_spend."""
    team = _TestTeam()
    scanner_findings = [{"title": "Cost test", "severity": "low"}]

    sdk_output = {
        "messages": [],
        "model": "claude-sonnet-4-20250514",
        "cost_usd": 0.05,
        "num_turns": 3,
    }

    mock_record = AsyncMock()
    with (
        patch(
            "app.agent_runtime.sdk.runner.run_sdk_session",
            AsyncMock(return_value=sdk_output),
        ),
        patch(
            "app.agent_runtime.redis_store.AgentRuntimeRedis",
        ) as mock_store_cls,
    ):
        mock_store_cls.return_value.record_spend = mock_record
        result = await team.augment_with_sdk(
            scanner_findings,
            event={"type": "test"},
            trust_level=TrustLevel.RECOMMENDER,
            budget_status=BudgetStatus.OK,
        )

    mock_record.assert_awaited_once_with(0.05)
    assert result == scanner_findings  # No SDK findings parsed from empty messages


@pytest.mark.asyncio
async def test_augment_returns_originals_on_sdk_failure():
    """SDK failure returns original scanner findings unchanged."""
    team = _TestTeam()
    scanner_findings = [{"title": "Test", "severity": "low"}]

    with patch(
        "app.agent_runtime.sdk.runner.run_sdk_session",
        AsyncMock(side_effect=Exception("SDK crashed")),
    ):
        result = await team.augment_with_sdk(
            scanner_findings,
            event={"type": "test"},
            trust_level=TrustLevel.RECOMMENDER,
            budget_status=BudgetStatus.OK,
        )

    assert result == scanner_findings


@pytest.mark.asyncio
async def test_run_full_pipeline_scan_then_augment():
    """TeamRunner.run() executes scan then augment pipeline."""
    team = _TestTeam()

    sdk_output = {
        "messages": [],
        "model": "claude-sonnet-4-20250514",
        "cost_usd": 0.0,
        "num_turns": 0,
    }

    with (
        patch.object(team, "_run_scanner", return_value=_mock_report()),
        patch(
            "app.agent_runtime.sdk.runner.run_sdk_session",
            AsyncMock(return_value=sdk_output),
        ),
    ):
        result = await team.run(event={"type": "test", "source": "test"})

    assert len(result) == 1
    assert result[0]["source_team"] == "test_team"


@pytest.mark.asyncio
async def test_run_skips_augment_when_no_findings():
    """TeamRunner.run() skips SDK augmentation when scanners find nothing."""
    team = _TestTeam()

    mock_sdk = AsyncMock()
    with (
        patch.object(
            team,
            "_run_scanner",
            return_value=AgentReport(agent="a", findings=[]),
        ),
        patch("app.agent_runtime.sdk.runner.run_sdk_session", mock_sdk),
    ):
        result = await team.run(event={"type": "test"})

    assert result == []
    mock_sdk.assert_not_called()
