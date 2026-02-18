"""Tests for engineering agent enhancements: cross-team findings, vault isolation,
circular imports, dead code, external intelligence, and production health.

Covers:
  - Lead: _load_cross_team_summaries() + Cross-Team Highlights in daily brief
  - Architect: _scan_vault_isolation, _scan_circular_imports, _scan_dead_code, intel wiring
  - PerfMonitor: _scan_production_health
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agents.shared.report import AgentReport, Finding


# ---------------------------------------------------------------------------
# Lead: Cross-team summaries
# ---------------------------------------------------------------------------


class TestLeadCrossTeam:
    """Test cross-team report loading and brief integration."""

    def test_cross_team_dirs_defined(self):
        from agents.lead.lead import _CROSS_TEAM_REPORT_DIRS

        assert "data" in _CROSS_TEAM_REPORT_DIRS
        assert "product" in _CROSS_TEAM_REPORT_DIRS
        assert "ops" in _CROSS_TEAM_REPORT_DIRS
        assert "finance" in _CROSS_TEAM_REPORT_DIRS
        assert "gtm" in _CROSS_TEAM_REPORT_DIRS
        assert len(_CROSS_TEAM_REPORT_DIRS) == 5

    def test_load_cross_team_summaries_returns_list(self):
        from agents.lead.lead import _load_cross_team_summaries

        result = _load_cross_team_summaries()
        assert isinstance(result, list)
        # Each item is (team_name, AgentReport)
        for team, report in result:
            assert isinstance(team, str)
            assert isinstance(report, AgentReport)

    def test_load_cross_team_summaries_ignores_missing_dirs(self, tmp_path):
        """Non-existent report dirs are silently skipped."""
        from agents.lead.lead import _load_cross_team_summaries

        fake_dirs = {"fake_team": tmp_path / "does_not_exist"}
        with patch("agents.lead.lead._CROSS_TEAM_REPORT_DIRS", fake_dirs):
            result = _load_cross_team_summaries()
        assert result == []

    def test_load_cross_team_summaries_reads_lead_reports(self, tmp_path):
        """Reads *_lead_latest.json files from report dirs."""
        from agents.lead.lead import _load_cross_team_summaries

        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        report = AgentReport(
            agent="test_lead",
            findings=[
                Finding(
                    id="TEST-1",
                    severity="high",
                    category="test",
                    title="Test finding",
                    detail="Detail",
                )
            ],
        )
        (report_dir / "test_lead_latest.json").write_text(report.serialize())

        with patch(
            "agents.lead.lead._CROSS_TEAM_REPORT_DIRS", {"test": report_dir}
        ):
            result = _load_cross_team_summaries()

        assert len(result) == 1
        team, loaded = result[0]
        assert team == "test"
        assert loaded.agent == "test_lead"
        assert len(loaded.findings) == 1

    def test_daily_brief_includes_cross_team_section(self, tmp_path):
        """Cross-Team Highlights section appears in daily brief when data exists."""
        from agents.lead.lead import generate_daily_brief

        # Create a mock engineering report
        eng_report = AgentReport(
            agent="architect",
            scan_duration_seconds=1.0,
            findings=[
                Finding(
                    id="ENG-1",
                    severity="medium",
                    category="lint",
                    title="Lint issue",
                    detail="Detail",
                )
            ],
        )

        # Create a mock cross-team report
        ct_report = AgentReport(
            agent="ops_lead",
            scan_duration_seconds=2.0,
            findings=[
                Finding(
                    id="OPS-1",
                    severity="high",
                    category="health",
                    title="Service degraded",
                    detail="Detail",
                )
            ],
        )

        report_dir = tmp_path / "reports"
        report_dir.mkdir()
        (report_dir / "ops_lead_latest.json").write_text(ct_report.serialize())

        with patch("agents.lead.lead._CROSS_TEAM_REPORT_DIRS", {"ops": report_dir}):
            brief = generate_daily_brief([eng_report])

        assert "Cross-Team Highlights" in brief
        assert "ops" in brief.lower()

    def test_daily_brief_works_without_cross_team_data(self):
        """Brief generates fine when no cross-team reports exist."""
        from agents.lead.lead import generate_daily_brief

        report = AgentReport(
            agent="architect",
            scan_duration_seconds=0.5,
            findings=[],
        )
        with patch("agents.lead.lead._CROSS_TEAM_REPORT_DIRS", {}):
            brief = generate_daily_brief([report])
        assert "Engineering Brief" in brief


# ---------------------------------------------------------------------------
# Architect: Vault isolation
# ---------------------------------------------------------------------------


class TestArchitectVaultIsolation:
    """Test vault isolation scanner."""

    def test_scan_vault_isolation_flags_unscoped_query(self, tmp_path):
        from agents.architect.architect import _scan_vault_isolation

        # Create a mock service file with an unscoped Contact query
        services_dir = tmp_path / "app" / "services"
        services_dir.mkdir(parents=True)
        (services_dir / "bad_service.py").write_text(
            textwrap.dedent("""\
            async def list_all_contacts(db):
                result = await db.execute(select(Contact))
                return result.scalars().all()
            """)
        )

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            _scan_vault_isolation(findings)

        vault_findings = [f for f in findings if f.category == "vault_isolation"]
        assert len(vault_findings) >= 1
        assert "Contact" in vault_findings[0].title

    def test_scan_vault_isolation_passes_scoped_query(self, tmp_path):
        from agents.architect.architect import _scan_vault_isolation

        services_dir = tmp_path / "app" / "services"
        services_dir.mkdir(parents=True)
        (services_dir / "good_service.py").write_text(
            textwrap.dedent("""\
            async def list_my_contacts(db, current_user):
                result = await db.execute(
                    select(Contact).where(Contact.user_id == current_user.id)
                )
                return result.scalars().all()
            """)
        )

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            _scan_vault_isolation(findings)

        vault_findings = [f for f in findings if f.category == "vault_isolation"]
        assert len(vault_findings) == 0


# ---------------------------------------------------------------------------
# Architect: Circular import detection
# ---------------------------------------------------------------------------


class TestArchitectCircularImports:
    """Test circular import detection."""

    def test_detects_simple_cycle(self, tmp_path):
        from agents.architect.architect import _scan_circular_imports

        # Create app/ with a circular import
        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "__init__.py").write_text("")

        (app_dir / "a.py").write_text("from app.b import something\n")
        (app_dir / "b.py").write_text("from app.a import something_else\n")

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            count = _scan_circular_imports(findings)

        assert count >= 1
        circ_findings = [f for f in findings if f.category == "circular_import"]
        assert len(circ_findings) >= 1

    def test_no_cycle_detected_for_linear_imports(self, tmp_path):
        from agents.architect.architect import _scan_circular_imports

        app_dir = tmp_path / "app"
        app_dir.mkdir()
        (app_dir / "__init__.py").write_text("")

        (app_dir / "a.py").write_text("from app.b import something\n")
        (app_dir / "b.py").write_text("import os\n")

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            count = _scan_circular_imports(findings)

        assert count == 0

    def test_returns_zero_when_no_app_dir(self, tmp_path):
        from agents.architect.architect import _scan_circular_imports

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            count = _scan_circular_imports(findings)

        assert count == 0


# ---------------------------------------------------------------------------
# Architect: Dead code detection
# ---------------------------------------------------------------------------


class TestArchitectDeadCode:
    """Test dead code detection."""

    def test_flags_unused_function(self, tmp_path):
        from agents.architect.architect import _scan_dead_code

        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
            def used_function():
                return 42

            def totally_orphaned_function():
                return "nobody calls me"

            result = used_function()
            """)
        )

        findings: list[Finding] = []
        py_files = [tmp_path / "module.py"]

        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            with patch("agents.architect.architect._py_files", return_value=[]):
                count = _scan_dead_code(py_files, findings)

        dead = [f for f in findings if f.category == "dead_code"]
        dead_names = [f.title for f in dead]
        assert any("totally_orphaned_function" in t for t in dead_names)

    def test_ignores_private_functions(self, tmp_path):
        from agents.architect.architect import _scan_dead_code

        (tmp_path / "module.py").write_text(
            textwrap.dedent("""\
            def _private_helper():
                return "private"
            """)
        )

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            with patch("agents.architect.architect._py_files", return_value=[]):
                _scan_dead_code([tmp_path / "module.py"], findings)

        dead = [f for f in findings if f.category == "dead_code"]
        assert not any("_private_helper" in f.title for f in dead)


# ---------------------------------------------------------------------------
# Architect: External intelligence wiring
# ---------------------------------------------------------------------------


class TestArchitectExternalIntel:
    """Test that architect scan wires in external intelligence."""

    def test_scan_includes_intel_notes(self):
        """architect.scan() doesn't crash when intelligence module is available."""
        from agents.architect.architect import scan

        report = scan()
        # The report should succeed (intel is optional)
        assert report.agent == "architect"
        assert isinstance(report.intelligence_applied, list)


# ---------------------------------------------------------------------------
# PerfMonitor: Production health check
# ---------------------------------------------------------------------------


class TestPerfMonitorProductionHealth:
    """Test production health check scanner."""

    def test_healthy_response_no_findings(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=True, status_code=200, response_ms=150.0)
        with patch(
            "agents.shared.api_client.check_health", return_value=mock_status
        ):
            findings, metrics = _scan_production_health()

        assert metrics["production_healthy"] is True
        assert metrics["production_response_ms"] == 150.0
        assert len(findings) == 0

    def test_unhealthy_response_critical_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=False, status_code=503, response_ms=0.0)
        with patch(
            "agents.shared.api_client.check_health", return_value=mock_status
        ):
            findings, metrics = _scan_production_health()

        assert metrics["production_healthy"] is False
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert "503" in findings[0].title

    def test_slow_response_high_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=True, status_code=200, response_ms=3000.0)
        with patch(
            "agents.shared.api_client.check_health", return_value=mock_status
        ):
            findings, metrics = _scan_production_health()

        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert "3000" in findings[0].title

    def test_elevated_latency_medium_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=True, status_code=200, response_ms=750.0)
        with patch(
            "agents.shared.api_client.check_health", return_value=mock_status
        ):
            findings, metrics = _scan_production_health()

        assert len(findings) == 1
        assert findings[0].severity == "medium"

    def test_graceful_when_api_client_unavailable(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health

        with patch.dict("sys.modules", {"agents.shared.api_client": None}):
            with patch(
                "agents.perf_monitor.perf_monitor._scan_production_health",
                wraps=_scan_production_health,
            ):
                findings, metrics = _scan_production_health()

        # Should not crash — either returns data or skips gracefully
        assert isinstance(findings, list)
        assert isinstance(metrics, dict)


# ---------------------------------------------------------------------------
# Integration: architect scan() includes new scanners
# ---------------------------------------------------------------------------


class TestArchitectScanIntegration:
    """Verify scan() includes the new scanners in its report."""

    def test_scan_has_new_metrics(self):
        from agents.architect.architect import scan

        report = scan()
        assert "circular_import_cycles" in report.metrics
        assert "dead_functions_detected" in report.metrics

    def test_scan_report_is_valid(self):
        from agents.architect.architect import scan

        report = scan()
        assert report.agent == "architect"
        assert report.scan_duration_seconds >= 0
        assert isinstance(report.findings, list)
