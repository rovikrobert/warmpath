"""Test data team execution integration."""

from agents.shared.execution_engine import ExecutionEngine, ExecutionTier
from agents.shared.report import Finding


def test_data_pipeline_retry_is_auto_do():
    engine = ExecutionEngine(enabled=True)
    f = Finding(
        id="data-1",
        severity="low",
        category="pipeline_retry",
        title="Stale enrichment batch",
        detail="Batch 42 failed, retryable",
        auto_fixable=True,
    )
    tier = engine.triage(f)
    assert tier == ExecutionTier.AUTO_DO


def test_data_team_process_findings():
    engine = ExecutionEngine(enabled=True)
    findings = [
        Finding(
            id="data-1",
            severity="low",
            category="pipeline_retry",
            title="Retry enrichment",
            detail="",
            auto_fixable=True,
        ),
        Finding(
            id="data-2",
            severity="medium",
            category="data_quality",
            title="Score drift detected",
            detail="",
            auto_fixable=False,
        ),
    ]
    summary = engine.process_findings(findings, team="data", dry_run=True)
    assert summary["team"] == "data"
    assert summary["total"] == 2
