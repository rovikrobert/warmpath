"""Tests for finance team subgraph wrapper."""

from unittest.mock import patch

from app.agent_runtime.teams.finance import FinanceTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_run_existing_scanners_returns_findings_with_finance_source_team():
    mock_report = AgentReport(
        agent="credits_manager",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="credit_economy",
                title="Credit expiry spike next month",
                detail="1200 credits expiring within 30 days across 45 users",
                file="app/services/credits.py",
                line=77,
                recommendation="Send proactive credit-use nudge emails",
                effort_hours=1.0,
            )
        ],
    )
    with patch.object(FinanceTeam, "_run_scanner", return_value=mock_report):
        findings = run_existing_scanners(["credits_manager"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Credit expiry spike next month"
        assert findings[0]["source_team"] == "finance"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(
        FinanceTeam, "_run_scanner", side_effect=Exception("Finance scan error")
    ):
        findings = run_existing_scanners(["credits_manager"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "Finance scan error" in findings[0]["title"]
        assert findings[0]["source_team"] == "finance"
