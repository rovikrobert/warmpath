"""Test the cross-team execution engine."""

import pytest
from unittest.mock import MagicMock, patch

from agents.shared.execution_engine import (
    ExecutionAction,
    ExecutionEngine,
    ExecutionResult,
    ExecutionTier,
)
from agents.shared.repair import RepairResult
from agents.shared.report import Finding


def _finding(id="f1", severity="low", auto_fixable=True, category="lint", file=None):
    return Finding(
        id=id,
        severity=severity,
        category=category,
        title="Test finding",
        detail="Detail",
        file=file,
        auto_fixable=auto_fixable,
    )


@pytest.mark.smoke
def test_triage_auto_do_for_trivial():
    engine = ExecutionEngine(enabled=True)
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_DO


@pytest.mark.smoke
def test_triage_auto_pr_for_medium():
    engine = ExecutionEngine(enabled=True)
    f = _finding(category="test_coverage", auto_fixable=False, severity="medium")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_PR


@pytest.mark.smoke
def test_triage_escalate_for_critical():
    engine = ExecutionEngine(enabled=True)
    f = _finding(severity="critical")
    tier = engine.triage(f)
    assert tier == ExecutionTier.ESCALATE


@pytest.mark.smoke
def test_triage_all_report_only_when_disabled():
    engine = ExecutionEngine(enabled=False)
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.REPORT_ONLY


@pytest.mark.smoke
def test_circuit_breaker_caps_auto_merges():
    engine = ExecutionEngine(enabled=True, max_auto_merges_per_day=2)
    engine._auto_merge_count = 2
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_PR


@pytest.mark.smoke
def test_execute_returns_result():
    engine = ExecutionEngine(enabled=True)
    f = _finding()
    result = engine.execute(f, ExecutionTier.REPORT_ONLY)
    assert isinstance(result, ExecutionResult)
    assert result.action == ExecutionAction.REPORTED


@pytest.mark.smoke
def test_process_findings_groups_by_tier():
    engine = ExecutionEngine(enabled=True)
    findings = [
        _finding(id="f1", category="lint", auto_fixable=True, severity="low"),
        _finding(
            id="f2", category="test_coverage", auto_fixable=False, severity="medium"
        ),
        _finding(id="f3", severity="critical"),
    ]
    summary = engine.process_findings(findings, team="engineering", dry_run=True)
    assert summary["auto_do_count"] == 1  # lint finding
    assert summary["auto_pr_count"] == 1  # test_coverage finding
    assert summary["escalate_count"] == 1  # critical finding


def test_execute_auto_do_calls_repair():
    """AUTO_DO tier must call repair_auto_fixable, not return fake results."""
    mock_repair = MagicMock(
        return_value=RepairResult(
            fixed_count=1,
            pr_url="https://github.com/org/repo/pull/42",
            fixed_ids=["f1"],
        )
    )
    with patch("agents.shared.execution_engine.repair_auto_fixable", mock_repair):
        engine = ExecutionEngine(enabled=True)
        f = _finding(id="f1", category="lint", auto_fixable=True, severity="low")
        result = engine.execute(f, ExecutionTier.AUTO_DO)
        mock_repair.assert_called_once()
        assert result.action == ExecutionAction.AUTO_FIXED
        assert result.pr_url == "https://github.com/org/repo/pull/42"


def test_execute_auto_pr_calls_repair():
    """AUTO_PR tier must call repair_auto_fixable, not return fake results."""
    mock_repair = MagicMock(
        return_value=RepairResult(
            fixed_count=1,
            pr_url="https://github.com/org/repo/pull/43",
            fixed_ids=["f2"],
        )
    )
    with patch("agents.shared.execution_engine.repair_auto_fixable", mock_repair):
        engine = ExecutionEngine(enabled=True)
        f = _finding(
            id="f2", category="test_coverage", auto_fixable=False, severity="medium"
        )
        result = engine.execute(f, ExecutionTier.AUTO_PR)
        mock_repair.assert_called_once()
        assert result.action == ExecutionAction.PR_CREATED
        assert result.pr_url == "https://github.com/org/repo/pull/43"


def test_execute_auto_do_returns_skipped_when_no_changes():
    """AUTO_DO returns SKIPPED when repair produces no changes."""
    mock_repair = MagicMock(return_value=RepairResult(fixed_count=0, skipped_count=1))
    with patch("agents.shared.execution_engine.repair_auto_fixable", mock_repair):
        engine = ExecutionEngine(enabled=True)
        f = _finding(id="f1", category="lint", auto_fixable=True, severity="low")
        result = engine.execute(f, ExecutionTier.AUTO_DO)
        assert result.action == ExecutionAction.SKIPPED
        assert result.pr_url is None


def test_execute_auto_do_handles_repair_exception():
    """AUTO_DO returns SKIPPED when repair raises an exception."""
    with patch(
        "agents.shared.execution_engine.repair_auto_fixable",
        side_effect=Exception("git push failed"),
    ):
        engine = ExecutionEngine(enabled=True)
        f = _finding(id="f1", category="lint", auto_fixable=True, severity="low")
        result = engine.execute(f, ExecutionTier.AUTO_DO)
        assert result.action == ExecutionAction.SKIPPED
        assert "git push failed" in result.detail


def test_execute_passes_finding_to_repair():
    """repair_auto_fixable receives the finding object for in-place status updates."""
    mock_repair = MagicMock(return_value=RepairResult(fixed_count=1, fixed_ids=["f1"]))
    with patch("agents.shared.execution_engine.repair_auto_fixable", mock_repair):
        engine = ExecutionEngine(enabled=True)
        f = _finding(id="f1", category="lint", auto_fixable=True, severity="low")
        engine.execute(f, ExecutionTier.AUTO_DO)
        # Verify repair was called with a list containing our finding
        mock_repair.assert_called_once_with([f])


def test_engine_reads_from_settings_not_env_only(monkeypatch):
    """ExecutionEngine should try app.config.settings before os.getenv."""
    import inspect

    import agents.shared.execution_engine as mod

    source = inspect.getsource(mod.ExecutionEngine.__init__)
    # Should reference settings, not just os.getenv
    assert "settings" in source.lower() or "config" in source.lower(), (
        "ExecutionEngine.__init__ should read from app.config.settings"
    )
