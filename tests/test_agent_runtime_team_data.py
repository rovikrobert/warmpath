"""Tests for data team subgraph wrapper."""

from unittest.mock import patch

from app.agent_runtime.teams.data import DataTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_run_existing_scanners_returns_findings_with_data_source_team():
    mock_report = AgentReport(
        agent="pipeline",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="data_quality",
                title="Stale enrichment cache",
                detail="Cache TTL expired for 200 contacts",
                file="app/services/enrichment.py",
                line=42,
                recommendation="Refresh enrichment cache",
                effort_hours=0.5,
            )
        ],
    )
    with patch.object(DataTeam, "_run_scanner", return_value=mock_report):
        findings = run_existing_scanners(["pipeline"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Stale enrichment cache"
        assert findings[0]["source_team"] == "data"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(
        DataTeam, "_run_scanner", side_effect=Exception("Pipeline check failed")
    ):
        findings = run_existing_scanners(["pipeline"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "Pipeline check failed" in findings[0]["title"]
        assert findings[0]["source_team"] == "data"
