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
