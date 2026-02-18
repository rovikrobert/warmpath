"""Tests for engineering agent enhancements: cross-team findings, vault isolation,
circular imports, dead code, mypy, mutation testing, external intelligence,
and production health.

Covers:
  - Lead: _load_cross_team_summaries() + Cross-Team Highlights in daily brief
  - Architect: _scan_vault_isolation, _scan_circular_imports, _scan_dead_code,
               _scan_mypy, _scan_mutation_testing, intel wiring
  - PerfMonitor: _scan_production_health
"""

from __future__ import annotations

import ast
import textwrap
from unittest.mock import MagicMock, patch


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

        with patch("agents.lead.lead._CROSS_TEAM_REPORT_DIRS", {"test": report_dir}):
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

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("agents.architect.architect._run_tool", return_value=mock_result):
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
        with patch("agents.shared.api_client.check_health", return_value=mock_status):
            findings, metrics = _scan_production_health()

        assert metrics["production_healthy"] is True
        assert metrics["production_response_ms"] == 150.0
        assert len(findings) == 0

    def test_unhealthy_response_critical_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=False, status_code=503, response_ms=0.0)
        with patch("agents.shared.api_client.check_health", return_value=mock_status):
            findings, metrics = _scan_production_health()

        assert metrics["production_healthy"] is False
        assert len(findings) == 1
        assert findings[0].severity == "critical"
        assert "503" in findings[0].title

    def test_slow_response_high_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=True, status_code=200, response_ms=3000.0)
        with patch("agents.shared.api_client.check_health", return_value=mock_status):
            findings, metrics = _scan_production_health()

        assert len(findings) == 1
        assert findings[0].severity == "high"
        assert "3000" in findings[0].title

    def test_elevated_latency_medium_finding(self):
        from agents.perf_monitor.perf_monitor import _scan_production_health
        from agents.shared.api_client import HealthStatus

        mock_status = HealthStatus(healthy=True, status_code=200, response_ms=750.0)
        with patch("agents.shared.api_client.check_health", return_value=mock_status):
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
# Architect: Mypy scanner
# ---------------------------------------------------------------------------


class TestArchitectMypy:
    """Test mypy type checking scanner."""

    def test_scan_mypy_unavailable(self):
        """Returns info finding when mypy is not installed."""
        from agents.architect.architect import _scan_mypy

        findings: list[Finding] = []
        with patch("agents.architect.architect._run_tool", return_value=None):
            metrics = _scan_mypy(findings)

        assert metrics["mypy_available"] is False
        assert len(findings) == 1
        assert findings[0].id == "ARCH-MYPY-UNAVAIL"

    def test_scan_mypy_zero_errors(self):
        """Reports info finding when mypy is clean."""
        from agents.architect.architect import _scan_mypy

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        findings: list[Finding] = []
        with patch("agents.architect.architect._run_tool", return_value=mock_result):
            metrics = _scan_mypy(findings)

        assert metrics["mypy_available"] is True
        assert metrics["mypy_errors"] == 0
        assert any(f.id == "ARCH-MYPY-CLEAN" for f in findings)

    def test_scan_mypy_few_errors(self):
        """Reports low severity for 10-50 errors."""
        from agents.architect.architect import _scan_mypy

        # Simulate 15 mypy errors
        lines = [
            f"app/services/svc{i}.py:{i}: error: Incompatible type [assignment]"
            for i in range(15)
        ]
        mock_result = MagicMock()
        mock_result.stdout = "\n".join(lines)

        findings: list[Finding] = []
        with patch("agents.architect.architect._run_tool", return_value=mock_result):
            metrics = _scan_mypy(findings)

        assert metrics["mypy_errors"] == 15
        mypy_findings = [f for f in findings if f.id == "ARCH-MYPY-ERRORS"]
        assert len(mypy_findings) == 1
        assert mypy_findings[0].severity == "low"

    def test_scan_mypy_many_errors(self):
        """Reports medium severity for >50 errors."""
        from agents.architect.architect import _scan_mypy

        lines = [f"app/services/svc.py:{i}: error: Bad type [misc]" for i in range(60)]
        mock_result = MagicMock()
        mock_result.stdout = "\n".join(lines)

        findings: list[Finding] = []
        with patch("agents.architect.architect._run_tool", return_value=mock_result):
            metrics = _scan_mypy(findings)

        assert metrics["mypy_errors"] == 60
        mypy_findings = [f for f in findings if f.id == "ARCH-MYPY-ERRORS"]
        assert len(mypy_findings) == 1
        assert mypy_findings[0].severity == "medium"

    def test_scan_mypy_parses_error_codes(self):
        """Error codes are correctly extracted and counted."""
        from agents.architect.architect import _scan_mypy

        mock_result = MagicMock()
        mock_result.stdout = (
            "app/a.py:1: error: Type mismatch [assignment]\n"
            "app/a.py:5: error: Missing return [return]\n"
            "app/b.py:3: error: Bad call [assignment]\n"
            "app/c.py:1: warning: Unused import [misc]\n"
        )

        findings: list[Finding] = []
        with patch("agents.architect.architect._run_tool", return_value=mock_result):
            metrics = _scan_mypy(findings)

        assert metrics["mypy_errors"] == 3
        assert metrics["mypy_warnings"] == 1
        assert metrics["mypy_error_codes"]["assignment"] == 2
        assert metrics["mypy_error_codes"]["return"] == 1


# ---------------------------------------------------------------------------
# Architect: Mutation testing
# ---------------------------------------------------------------------------


class TestArchitectMutationTesting:
    """Test lightweight mutation testing sampler."""

    def test_collect_mutation_sites_finds_comparisons(self):
        """Collects compare_swap sites from source code."""
        from agents.architect.architect import _collect_mutation_sites

        source = textwrap.dedent("""\
        def check(x):
            if x > 0:
                return True
            return False
        """)
        sites = _collect_mutation_sites(source)
        types = [t for _, t in sites]
        assert "compare_swap" in types
        assert "return_none" in types

    def test_collect_mutation_sites_handles_syntax_error(self):
        from agents.architect.architect import _collect_mutation_sites

        sites = _collect_mutation_sites("def bad(:\n")
        assert sites == []

    def test_apply_mutation_compare_swap(self):
        """Applies operator swap mutation correctly."""
        from agents.architect.architect import _apply_mutation

        source = textwrap.dedent("""\
        def check(x):
            if x > 0:
                return True
        """)
        # Line 2 has the comparison x > 0
        mutated = _apply_mutation(source, 2, "compare_swap")
        assert mutated is not None
        # The > should become <=
        tree = ast.parse(mutated)
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and node.ops:
                assert isinstance(node.ops[0], ast.LtE)

    def test_apply_mutation_return_none(self):
        """Applies return-None mutation correctly."""
        from agents.architect.architect import _apply_mutation

        source = textwrap.dedent("""\
        def get_value():
            return 42
        """)
        mutated = _apply_mutation(source, 2, "return_none")
        assert mutated is not None
        assert "None" in mutated or "return None" in mutated

    def test_apply_mutation_wrong_line_returns_none(self):
        """Returns None when mutation can't be applied at target line."""
        from agents.architect.architect import _apply_mutation

        source = "def f():\n    pass\n"
        result = _apply_mutation(source, 999, "compare_swap")
        assert result is None

    def test_scan_mutation_testing_all_targets_missing(self, tmp_path):
        """Returns empty metrics when no target files exist."""
        from agents.architect.architect import _scan_mutation_testing

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            metrics = _scan_mutation_testing(findings)

        assert metrics["mutation_files_tested"] == 0
        assert metrics["mutation_total_tested"] == 0

    def test_scan_mutation_testing_runs_and_restores(self, tmp_path):
        """Mutation testing writes mutations, runs pytest, restores original."""
        from agents.architect.architect import _scan_mutation_testing

        # Create a target file
        svc_dir = tmp_path / "app" / "services"
        svc_dir.mkdir(parents=True)
        target = svc_dir / "warm_scorer.py"
        original_code = textwrap.dedent("""\
        def score(x):
            if x > 0:
                return 100
            return 0
        """)
        target.write_text(original_code)

        # Mock _run_tool for pytest: return failure (= mutation killed)
        mock_pytest_result = MagicMock()
        mock_pytest_result.returncode = 1  # tests caught the mutation

        findings: list[Finding] = []
        with patch("agents.architect.architect.PROJECT_ROOT", tmp_path):
            with patch(
                "agents.architect.architect._run_tool", return_value=mock_pytest_result
            ):
                metrics = _scan_mutation_testing(findings)

        # Original file should be restored
        assert target.read_text() == original_code
        assert metrics["mutation_files_tested"] >= 1
        assert metrics["mutation_killed"] >= 1

    def test_mutation_visitor_applies_once(self):
        """_MutationVisitor only applies one mutation."""
        from agents.architect.architect import _MutationVisitor

        source = textwrap.dedent("""\
        def f(x, y):
            if x > 0:
                pass
            if y > 0:
                pass
        """)
        tree = ast.parse(source)
        visitor = _MutationVisitor(target_line=2, mutation_type="compare_swap")
        new_tree = visitor.visit(tree)
        assert visitor.applied is True

        # Only line 2 should be mutated, line 4 should remain >
        compares = [n for n in ast.walk(new_tree) if isinstance(n, ast.Compare)]
        assert len(compares) == 2
        # First compare (line 2) should be mutated to LtE
        assert isinstance(compares[0].ops[0], ast.LtE)
        # Second compare (line 4) should stay as Gt
        assert isinstance(compares[1].ops[0], ast.Gt)


# ---------------------------------------------------------------------------
# Integration: architect scan() includes new scanners
# ---------------------------------------------------------------------------


class TestArchitectScanIntegration:
    """Verify scan() includes the new scanners in its report."""

    def test_scan_has_new_metrics(self):
        from agents.architect.architect import scan

        # Mock the external tools to avoid real mypy/pytest calls during test
        mock_mypy = MagicMock()
        mock_mypy.stdout = ""
        mock_mypy.returncode = 0

        with patch("agents.architect.architect._run_tool", return_value=mock_mypy):
            report = scan()

        assert "circular_import_cycles" in report.metrics
        assert "dead_functions_detected" in report.metrics
        assert "mypy_available" in report.metrics
        assert "mutation_files_tested" in report.metrics

    def test_scan_report_is_valid(self):
        from agents.architect.architect import scan

        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.returncode = 0

        with patch("agents.architect.architect._run_tool", return_value=mock_result):
            report = scan()

        assert report.agent == "architect"
        assert report.scan_duration_seconds >= 0
        assert isinstance(report.findings, list)
