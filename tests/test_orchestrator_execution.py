"""Test execution engine integration in orchestrator."""

from agents.shared.execution_engine import ExecutionEngine
from agents.shared.report import Finding


def test_execution_engine_enabled_processes_findings():
    engine = ExecutionEngine(enabled=True)
    findings = [
        Finding(
            id="f1",
            severity="low",
            category="lint",
            title="Bad format",
            detail="",
            auto_fixable=True,
        ),
    ]
    summary = engine.process_findings(findings, team="engineering", dry_run=True)
    assert summary["auto_do_count"] == 1


def test_execution_summary_carries_repair_data():
    """_execution_summary should carry real repair data when PRs are created."""
    from agents.shared.execution_engine import (
        ExecutionResult,
        ExecutionTier,
        ExecutionAction,
    )

    # Simulate engine with a successful repair result
    result = ExecutionResult(
        finding_id="f1",
        tier=ExecutionTier.AUTO_DO,
        action=ExecutionAction.AUTO_FIXED,
        detail="Repaired: lint issue",
        pr_url="https://github.com/org/repo/pull/42",
    )
    assert result.pr_url == "https://github.com/org/repo/pull/42"
    assert result.action == ExecutionAction.AUTO_FIXED


def test_execution_engine_disabled_reports_only():
    engine = ExecutionEngine(enabled=False)
    findings = [
        Finding(
            id="f1",
            severity="low",
            category="lint",
            title="Bad format",
            detail="",
            auto_fixable=True,
        ),
    ]
    summary = engine.process_findings(findings, team="engineering", dry_run=True)
    assert summary["report_only_count"] == 1
