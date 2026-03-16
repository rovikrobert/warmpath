"""Tests for agent finding confidence gating — prevents low-confidence data
from surfacing as high-severity findings in Telegram reports.

Covers:
- Data analyst: sample-size gating on retention/activation findings
- Finance investor_relations: environment validation on test count verification
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import MagicMock, patch

from agents.shared.report import Finding


# ---------------------------------------------------------------------------
# Data analyst: retention sample-size gating
# ---------------------------------------------------------------------------


class TestRetentionSampleSizeGating:
    """_scan_cohort_retention should suppress findings when n < 30."""

    def _run_scan(self, retention_rows, activation_rows=None):
        """Helper: run _scan_cohort_retention with given mock data."""
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list = []
        metrics: dict = {}

        with patch("data_team.shared.query_executor.get_executor") as mock_get:
            mock_qe = MagicMock()
            mock_qe.is_available.return_value = True
            mock_qe.execute_template.side_effect = lambda name, _: {
                "signup_cohort_retention": retention_rows,
                "signup_cohort_activation": activation_rows or [],
            }.get(name, [])
            mock_get.return_value = mock_qe

            _scan_cohort_retention(findings, insights, metrics)

        return findings, insights, metrics

    def test_small_sample_suppresses_retention_finding(self):
        """With <30 users, retention finding should NOT be created."""
        rows = [
            {"cohort_size": 5, "retained_week_2": 0},
            {"cohort_size": 3, "retained_week_2": 0},
        ]
        findings, insights, metrics = self._run_scan(rows)

        # No high-severity retention finding
        retention_findings = [f for f in findings if f.id == "analyst-cohort-001"]
        assert len(retention_findings) == 0

        # Metrics still recorded
        assert metrics["cohort_total_users"] == 8
        assert metrics["avg_week2_retention"] == 0.0

    def test_large_sample_allows_retention_finding(self):
        """With >=30 users and low retention, finding should be created."""
        rows = [
            {"cohort_size": 20, "retained_week_2": 1},
            {"cohort_size": 20, "retained_week_2": 2},
        ]
        findings, insights, metrics = self._run_scan(rows)

        retention_findings = [f for f in findings if f.id == "analyst-cohort-001"]
        assert len(retention_findings) == 1
        assert "40 users" in retention_findings[0].detail

    def test_large_sample_good_retention_no_finding(self):
        """With >=30 users and healthy retention, no finding."""
        rows = [
            {"cohort_size": 50, "retained_week_2": 20},
            {"cohort_size": 50, "retained_week_2": 25},
        ]
        findings, _, metrics = self._run_scan(rows)

        retention_findings = [f for f in findings if f.id == "analyst-cohort-001"]
        assert len(retention_findings) == 0
        assert metrics["avg_week2_retention"] > 0.20

    def test_insight_confidence_reflects_sample_size(self):
        """Insight should have low confidence when sample is small."""
        small_rows = [{"cohort_size": 5, "retained_week_2": 0}]
        _, insights, _ = self._run_scan(small_rows)

        assert len(insights) >= 1
        retention_insight = next(
            (i for i in insights if i.id == "analyst-insight-retention"), None
        )
        assert retention_insight is not None
        assert retention_insight.confidence < 0.5  # Low confidence for small sample

    def test_insight_confidence_high_for_large_sample(self):
        """Insight should have high confidence when sample is large."""
        large_rows = [
            {"cohort_size": 50, "retained_week_2": 20},
            {"cohort_size": 50, "retained_week_2": 25},
        ]
        _, insights, _ = self._run_scan(large_rows)

        retention_insight = next(
            (i for i in insights if i.id == "analyst-insight-retention"), None
        )
        assert retention_insight is not None
        assert retention_insight.confidence >= 0.8

    def test_activation_small_sample_suppressed(self):
        """Activation finding should also be suppressed for small samples."""
        retention_rows = [{"cohort_size": 5, "retained_week_2": 3}]
        activation_rows = [
            {"cohort_size": 5, "activated": 0},
            {"cohort_size": 3, "activated": 0},
        ]
        findings, _, _ = self._run_scan(retention_rows, activation_rows)

        activation_findings = [f for f in findings if f.id == "analyst-cohort-002"]
        assert len(activation_findings) == 0

    def test_activation_large_sample_allowed(self):
        """Activation finding should surface for large samples with low activation."""
        retention_rows = [{"cohort_size": 50, "retained_week_2": 40}]
        activation_rows = [
            {"cohort_size": 20, "activated": 2},
            {"cohort_size": 20, "activated": 1},
        ]
        findings, _, _ = self._run_scan(retention_rows, activation_rows)

        activation_findings = [f for f in findings if f.id == "analyst-cohort-002"]
        assert len(activation_findings) == 1

    def test_db_unavailable_no_crash(self):
        """When DB is unavailable, scan completes without error."""
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list = []
        metrics: dict = {}

        with patch("data_team.shared.query_executor.get_executor") as mock_get:
            mock_qe = MagicMock()
            mock_qe.is_available.return_value = False
            mock_get.return_value = mock_qe

            _scan_cohort_retention(findings, insights, metrics)

        assert metrics.get("cohort_analysis_available") is False
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Finance: test count environment validation
# ---------------------------------------------------------------------------


class TestTestCountEnvironmentValidation:
    """_check_test_count_claims should handle env failures gracefully."""

    def _run_check(
        self, claimed_count, pytest_stdout, pytest_returncode, regex_count=0
    ):
        """Helper: run _check_test_count_claims with mocked subprocess + files."""
        from finance_team.investor_relations.investor_relations import (
            _check_test_count_claims,
        )

        findings: list[Finding] = []
        fin_findings: list = []
        metrics: dict = {}

        # Mock CLAUDE.md to contain claimed count
        claude_md_content = f"**{claimed_count} tests passing.**"

        with (
            patch(
                "finance_team.investor_relations.investor_relations._read_safe",
                return_value=claude_md_content,
            ),
            patch("subprocess.run") as mock_run,
            patch(
                "finance_team.investor_relations.investor_relations.TESTS_DIR"
            ) as mock_tests_dir,
        ):
            mock_result = MagicMock()
            mock_result.stdout = pytest_stdout
            mock_result.returncode = pytest_returncode
            mock_run.return_value = mock_result

            # Mock TESTS_DIR.glob to return regex_count test files
            mock_files = []
            for i in range(regex_count):
                mock_file = MagicMock()
                mock_file.stem = f"test_{i}"
                mock_files.append(mock_file)
            mock_tests_dir.glob.return_value = mock_files

            _check_test_count_claims(findings, fin_findings, metrics)

        return findings, fin_findings, metrics

    def test_pytest_fails_with_zero_tests_suppresses_high_severity(self):
        """When pytest collection fails (rc!=0, 0 tests), don't claim 100% drift."""
        findings, fin_findings, metrics = self._run_check(
            claimed_count=3038,
            pytest_stdout="",  # No output — pytest failed
            pytest_returncode=2,  # Collection error
            regex_count=0,
        )

        # Should NOT produce ir-tests-001 (the high-severity "off by 100%")
        high_findings = [f for f in findings if f.id == "ir-tests-001"]
        assert len(high_findings) == 0

        # Should produce ir-tests-002 (low-severity "inconclusive")
        inconclusive = [f for f in findings if f.id == "ir-tests-002"]
        assert len(inconclusive) == 1
        assert inconclusive[0].severity == "low"
        assert "inconclusive" in inconclusive[0].title.lower()

    def test_pytest_succeeds_with_real_count(self):
        """When pytest works, normal delta logic applies."""
        findings, fin_findings, metrics = self._run_check(
            claimed_count=3038,
            pytest_stdout="3038 tests collected\n",
            pytest_returncode=0,
        )

        # No finding — counts match
        assert len(findings) == 0
        assert metrics["test_count_method"] == "pytest"

    def test_pytest_succeeds_with_drift(self):
        """When pytest works but count drifted >30%, report it."""
        findings, fin_findings, metrics = self._run_check(
            claimed_count=3038,
            pytest_stdout="1500 tests collected\n",
            pytest_returncode=0,
        )

        high_findings = [f for f in findings if f.id == "ir-tests-001"]
        assert len(high_findings) == 1
        assert high_findings[0].severity == "high"

    def test_method_tracked_in_metrics(self):
        """Metrics should indicate whether pytest or regex was used."""
        _, _, metrics = self._run_check(
            claimed_count=3038,
            pytest_stdout="3038 tests collected\n",
            pytest_returncode=0,
        )
        assert metrics["test_count_method"] == "pytest"
