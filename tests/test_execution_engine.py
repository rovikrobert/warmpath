"""Test the cross-team execution engine."""

from agents.shared.execution_engine import (
    ExecutionAction,
    ExecutionEngine,
    ExecutionResult,
    ExecutionTier,
)
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


def test_triage_auto_do_for_trivial():
    engine = ExecutionEngine(enabled=True)
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_DO


def test_triage_auto_pr_for_medium():
    engine = ExecutionEngine(enabled=True)
    f = _finding(category="test_coverage", auto_fixable=False, severity="medium")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_PR


def test_triage_escalate_for_critical():
    engine = ExecutionEngine(enabled=True)
    f = _finding(severity="critical")
    tier = engine.triage(f)
    assert tier == ExecutionTier.ESCALATE


def test_triage_all_report_only_when_disabled():
    engine = ExecutionEngine(enabled=False)
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.REPORT_ONLY


def test_circuit_breaker_caps_auto_merges():
    engine = ExecutionEngine(enabled=True, max_auto_merges_per_day=2)
    engine._auto_merge_count = 2
    f = _finding(category="lint", auto_fixable=True, severity="low")
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_PR


def test_execute_returns_result():
    engine = ExecutionEngine(enabled=True)
    f = _finding()
    result = engine.execute(f, ExecutionTier.REPORT_ONLY)
    assert isinstance(result, ExecutionResult)
    assert result.action == ExecutionAction.REPORTED


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
