"""Tests for product team subgraph wrapper."""

from unittest.mock import patch

from app.agent_runtime.teams.product import ProductTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_run_existing_scanners_returns_findings_with_product_source_team():
    mock_report = AgentReport(
        agent="ux_lead",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="ux",
                title="Onboarding drop-off at step 3",
                detail="40% of users abandon onboarding at CSV upload step",
                file="frontend/src/pages/Onboarding.jsx",
                line=120,
                recommendation="Simplify CSV upload step with drag-and-drop",
                effort_hours=2.0,
            )
        ],
    )
    with patch.object(ProductTeam, "_run_scanner", return_value=mock_report):
        findings = run_existing_scanners(["ux_lead"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Onboarding drop-off at step 3"
        assert findings[0]["source_team"] == "product"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(
        ProductTeam, "_run_scanner", side_effect=Exception("UX scan crashed")
    ):
        findings = run_existing_scanners(["ux_lead"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "UX scan crashed" in findings[0]["title"]
        assert findings[0]["source_team"] == "product"
