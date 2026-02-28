"""Tests for GTM team subgraph wrapper."""

from unittest.mock import patch

from app.agent_runtime.teams.gtm import GtmTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_run_existing_scanners_returns_findings_with_gtm_source_team():
    mock_report = AgentReport(
        agent="stratops",
        findings=[
            Finding(
                id="f1",
                severity="low",
                category="competitive",
                title="Competitor launched referral feature",
                detail="LinkedIn added employee referral tracking",
                file="gtm_team/stratops/scanner.py",
                line=30,
                recommendation="Analyze competitive positioning impact",
                effort_hours=2.0,
            )
        ],
    )
    with patch.object(GtmTeam, "_run_scanner", return_value=mock_report):
        findings = run_existing_scanners(["stratops"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Competitor launched referral feature"
        assert findings[0]["source_team"] == "gtm"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(GtmTeam, "_run_scanner", side_effect=Exception("GTM scan error")):
        findings = run_existing_scanners(["stratops"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "GTM scan error" in findings[0]["title"]
        assert findings[0]["source_team"] == "gtm"
