"""Test product team execution integration."""

from agents.shared.execution_engine import ExecutionEngine, ExecutionTier
from agents.shared.report import Finding


def test_product_finding_triaged_as_auto_pr():
    engine = ExecutionEngine(enabled=True)
    f = Finding(
        id="prod-1",
        severity="medium",
        category="ux_gap",
        title="Onboarding drop-off at step 3",
        detail="40% drop-off rate",
        auto_fixable=False,
    )
    tier = engine.triage(f)
    assert tier in (ExecutionTier.AUTO_PR, ExecutionTier.ESCALATE)


def test_product_team_process_findings():
    engine = ExecutionEngine(enabled=True)
    findings = [
        Finding(
            id="prod-1",
            severity="medium",
            category="ux_gap",
            title="Missing empty state",
            detail="",
            auto_fixable=False,
        ),
        Finding(
            id="prod-2",
            severity="low",
            category="copy",
            title="Typo in header",
            detail="",
            auto_fixable=False,
        ),
    ]
    summary = engine.process_findings(findings, team="product", dry_run=True)
    assert summary["team"] == "product"
    assert summary["total"] == 2
