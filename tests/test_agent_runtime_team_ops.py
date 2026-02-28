"""Tests for ops team subgraph wrapper."""

from unittest.mock import patch

from app.agent_runtime.teams.ops import OpsTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_run_existing_scanners_returns_findings_with_ops_source_team():
    mock_report = AgentReport(
        agent="marsh",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="marketplace",
                title="Low marketplace supply at target companies",
                detail="Only 3 network holders cover top 10 target companies",
                file="app/services/marketplace.py",
                line=88,
                recommendation="Activate NH recruitment campaign",
                effort_hours=4.0,
            )
        ],
    )
    with patch.object(OpsTeam, "_run_scanner", return_value=mock_report):
        findings = run_existing_scanners(["marsh"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Low marketplace supply at target companies"
        assert findings[0]["source_team"] == "ops"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(
        OpsTeam, "_run_scanner", side_effect=Exception("Ops scan failed")
    ):
        findings = run_existing_scanners(["marsh"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "Ops scan failed" in findings[0]["title"]
        assert findings[0]["source_team"] == "ops"
