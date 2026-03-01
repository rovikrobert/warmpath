"""Tests for engineering team subgraph wrapper."""

import importlib
from unittest.mock import patch

from app.agent_runtime.teams.engineering import EngineeringTeam, run_existing_scanners
from agents.shared.report import AgentReport, Finding


def test_all_scanner_module_paths_are_importable():
    """Every scanner_modules path resolves to a real Python module."""
    for name, path in EngineeringTeam.scanner_modules.items():
        mod = importlib.import_module(path)
        assert mod is not None, f"Scanner '{name}' path '{path}' failed to import"


def test_run_existing_scanners_returns_findings_list():
    mock_report = AgentReport(
        agent="architect",
        findings=[
            Finding(
                id="f1",
                severity="medium",
                category="lint",
                title="Unused import",
                detail="os imported but unused",
                file="app/main.py",
                line=5,
                recommendation="Remove unused import",
                effort_hours=0.1,
            )
        ],
    )
    with patch.object(
        EngineeringTeam,
        "_run_scanner",
        return_value=mock_report,
    ):
        findings = run_existing_scanners(["architect"])
        assert len(findings) == 1
        assert findings[0]["title"] == "Unused import"
        assert findings[0]["severity"] == "medium"
        assert findings[0]["source_team"] == "engineering"


def test_run_existing_scanners_handles_scanner_failure():
    with patch.object(
        EngineeringTeam,
        "_run_scanner",
        side_effect=Exception("Scanner crashed"),
    ):
        findings = run_existing_scanners(["architect"])
        assert len(findings) == 1
        assert findings[0]["severity"] == "high"
        assert "Scanner crashed" in findings[0]["title"]
