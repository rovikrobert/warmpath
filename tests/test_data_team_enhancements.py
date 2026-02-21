"""Tests for data team enhancements: query executor, anomaly detection,
cohort analysis, warm score calibration, A/B testing, live data quality,
intelligence freshness, live KPIs.

All tests mock the query executor to avoid requiring a live database.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import MagicMock, patch


from agents.shared.report import Finding
from data_team.shared.report import Insight


# ---------------------------------------------------------------------------
# QueryExecutor
# ---------------------------------------------------------------------------


class TestQueryExecutor:
    """Test query executor initialisation and execution."""

    def test_unavailable_without_database_url(self):
        from data_team.shared.query_executor import QueryExecutor

        with patch.dict("os.environ", {}, clear=True):
            qe = QueryExecutor()
        assert qe.is_available() is False

    def test_execute_template_returns_empty_when_unavailable(self):
        from data_team.shared.query_executor import QueryExecutor

        with patch.dict("os.environ", {}, clear=True):
            qe = QueryExecutor()
        result = qe.execute_template("daily_signups", {"start_date": "2024-01-01"})
        assert result == []

    def test_execute_sql_returns_empty_when_unavailable(self):
        from data_team.shared.query_executor import QueryExecutor

        with patch.dict("os.environ", {}, clear=True):
            qe = QueryExecutor()
        result = qe.execute_sql("SELECT 1", {})
        assert result == []

    def test_cache_key_deterministic(self):
        from data_team.shared.query_executor import QueryExecutor

        key1 = QueryExecutor._cache_key("SELECT 1", {"a": 1})
        key2 = QueryExecutor._cache_key("SELECT 1", {"a": 1})
        assert key1 == key2

    def test_cache_key_varies_with_params(self):
        from data_team.shared.query_executor import QueryExecutor

        key1 = QueryExecutor._cache_key("SELECT 1", {"a": 1})
        key2 = QueryExecutor._cache_key("SELECT 1", {"a": 2})
        assert key1 != key2

    def test_unknown_template_returns_empty(self):
        from data_team.shared.query_executor import QueryExecutor

        qe = QueryExecutor()
        # Force available to test template lookup
        qe._available = True
        result = qe.execute_template("nonexistent_template")
        assert result == []

    def test_query_count_starts_at_zero(self):
        from data_team.shared.query_executor import QueryExecutor

        with patch.dict("os.environ", {}, clear=True):
            qe = QueryExecutor()
        assert qe.query_count == 0

    def test_clear_cache(self):
        from data_team.shared.query_executor import QueryExecutor

        with patch.dict("os.environ", {}, clear=True):
            qe = QueryExecutor()
        qe._cache["test"] = (999999999999, [{"a": 1}])
        qe.clear_cache()
        assert qe._cache == {}


# ---------------------------------------------------------------------------
# Pipeline: live data quality
# ---------------------------------------------------------------------------


class TestPipelineLiveDataQuality:
    """Test _scan_live_data_quality with mocked executor."""

    def _make_mock_executor(self, row_counts: dict[str, int], staleness_rows=None):
        """Create a mock executor that returns controlled row counts."""
        mock = MagicMock()
        mock.is_available.return_value = True

        def execute_sql(sql, params=None, context=""):
            # Row count queries
            for table, count in row_counts.items():
                if f"FROM {table}" in sql:
                    return [{"cnt": count}]
            # Staleness query
            if "MAX(created_at)" in sql:
                return staleness_rows if staleness_rows else []
            return []

        mock.execute_sql.side_effect = execute_sql
        return mock

    def test_reports_empty_tables(self):
        from data_team.pipeline.pipeline import _scan_live_data_quality

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        # 15 users (above pre-launch threshold) but other tables empty
        mock_qe = self._make_mock_executor(
            {
                "users": 15,
                "contacts": 5,
                "csv_uploads": 0,
                "search_requests": 0,
                "marketplace_listings": 0,
                "intro_facilitations": 0,
                "credit_transactions": 0,
            }
        )

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_live_data_quality(findings, insights, metrics)

        assert metrics["live_db_available"] is True
        assert metrics["live_empty_tables"] == 5
        assert any(f.id == "pipe-010" for f in findings)
        empty_finding = next(f for f in findings if f.id == "pipe-010")
        assert empty_finding.severity == "medium"

    def test_suppresses_empty_tables_prelaunch(self):
        from data_team.pipeline.pipeline import _scan_live_data_quality

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        # < 10 users → pre-launch, suppress empty table findings
        mock_qe = self._make_mock_executor(
            {
                "users": 0,
                "contacts": 0,
                "csv_uploads": 0,
                "search_requests": 0,
                "marketplace_listings": 0,
                "intro_facilitations": 0,
                "credit_transactions": 0,
            }
        )

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_live_data_quality(findings, insights, metrics)

        assert metrics["live_empty_tables"] == 7
        assert not any(f.id == "pipe-010" for f in findings)
        assert metrics.get("live_empty_suppressed") == "pre-launch (<10 users)"

    def test_healthy_data_no_findings(self):
        from data_team.pipeline.pipeline import _scan_live_data_quality

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = self._make_mock_executor(
            {
                "users": 100,
                "contacts": 5000,
                "csv_uploads": 50,
                "search_requests": 200,
                "marketplace_listings": 300,
                "intro_facilitations": 40,
                "credit_transactions": 150,
            }
        )

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_live_data_quality(findings, insights, metrics)

        assert metrics["live_empty_tables"] == 0
        assert not any(f.id == "pipe-010" for f in findings)
        assert metrics["live_total_rows"] == 5840

    def test_skips_when_db_unavailable(self):
        from data_team.pipeline.pipeline import _scan_live_data_quality

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_live_data_quality(findings, insights, metrics)

        assert metrics["live_db_available"] is False
        assert len(findings) == 0

    def test_staleness_detected(self):
        from datetime import datetime, timezone, timedelta
        from data_team.pipeline.pipeline import _scan_live_data_quality

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        old_time = datetime.now(timezone.utc) - timedelta(hours=100)
        mock_qe = self._make_mock_executor(
            {
                "users": 10,
                "contacts": 50,
                "csv_uploads": 5,
                "search_requests": 10,
                "marketplace_listings": 20,
                "intro_facilitations": 5,
                "credit_transactions": 10,
            },
            staleness_rows=[{"latest": old_time}],
        )

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_live_data_quality(findings, insights, metrics)

        assert any(f.id == "pipe-011" for f in findings)


# ---------------------------------------------------------------------------
# Analyst: anomaly detection
# ---------------------------------------------------------------------------


class TestAnalystAnomalyDetection:
    """Test Z-score anomaly detection on WAU and credit flow."""

    def test_detect_zsco[RESEND_KEY_REDACTED](self):
        from data_team.analyst.analyst import _detect_zsco[RESEND_KEY_REDACTED]

        values = [100, 102, 98, 101, 99, 103, 100]
        assert _detect_zsco[RESEND_KEY_REDACTED](values) is None

    def test_detect_zsco[RESEND_KEY_REDACTED](self):
        from data_team.analyst.analyst import _detect_zsco[RESEND_KEY_REDACTED]

        values = [100, 102, 98, 101, 99, 103, 200]
        result = _detect_zsco[RESEND_KEY_REDACTED](values)
        assert result is not None
        assert result["direction"] == "high"
        assert result["z_score"] > 2.0

    def test_detect_zsco[RESEND_KEY_REDACTED](self):
        from data_team.analyst.analyst import _detect_zsco[RESEND_KEY_REDACTED]

        values = [100, 102, 98, 101, 99, 103, 10]
        result = _detect_zsco[RESEND_KEY_REDACTED](values)
        assert result is not None
        assert result["direction"] == "low"

    def test_detect_zsco[RESEND_KEY_REDACTED](self):
        from data_team.analyst.analyst import _detect_zsco[RESEND_KEY_REDACTED]

        assert _detect_zsco[RESEND_KEY_REDACTED]([1, 2, 3]) is None

    def test_detect_zsco[RESEND_KEY_REDACTED](self):
        from data_team.analyst.analyst import _detect_zsco[RESEND_KEY_REDACTED]

        assert _detect_zsco[RESEND_KEY_REDACTED]([5, 5, 5, 5, 5]) is None

    def test_scan_anomaly_wau_drop(self):
        from data_team.analyst.analyst import _scan_anomaly_detection

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "weekly_active_users": [
                {"active_users": 100},
                {"active_users": 102},
                {"active_users": 98},
                {"active_users": 101},
                {"active_users": 99},
                {"active_users": 10},
            ],
            "credit_flow": [],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_anomaly_detection(findings, insights, metrics)

        assert metrics["anomaly_detection_available"] is True
        assert metrics["anomalies_detected"] >= 1
        assert any("WAU" in f.title for f in findings)

    def test_scan_anomaly_credit_imbalance(self):
        from data_team.analyst.analyst import _scan_anomaly_detection

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "weekly_active_users": [],
            "credit_flow": [
                {
                    "transaction_type": "earn_upload",
                    "tx_count": 50,
                    "total_amount": 5000,
                },
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_anomaly_detection(findings, insights, metrics)

        assert metrics["credit_earn_count"] == 50
        assert metrics["credit_spend_count"] == 0
        assert any("demand side inactive" in f.title for f in findings)

    def test_scan_anomaly_skips_when_unavailable(self):
        from data_team.analyst.analyst import _scan_anomaly_detection

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_anomaly_detection(findings, insights, metrics)

        assert metrics["anomaly_detection_available"] is False
        assert len(findings) == 0


# ---------------------------------------------------------------------------
# Analyst: cohort retention
# ---------------------------------------------------------------------------


class TestAnalystCohortRetention:
    """Test cohort retention analysis."""

    def test_low_retention_flagged(self):
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "signup_cohort_retention": [
                {
                    "cohort_week": "2024-01-01",
                    "cohort_size": 100,
                    "retained_week_2": 10,
                },
                {"cohort_week": "2024-01-08", "cohort_size": 80, "retained_week_2": 8},
            ],
            "signup_cohort_activation": [
                {"cohort_week": "2024-01-01", "cohort_size": 100, "activated": 30},
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_cohort_retention(findings, insights, metrics)

        assert metrics["avg_week2_retention"] == 0.1
        assert any(f.id == "analyst-cohort-001" for f in findings)

    def test_healthy_retention_no_finding(self):
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "signup_cohort_retention": [
                {
                    "cohort_week": "2024-01-01",
                    "cohort_size": 100,
                    "retained_week_2": 40,
                },
                {"cohort_week": "2024-01-08", "cohort_size": 80, "retained_week_2": 30},
            ],
            "signup_cohort_activation": [
                {"cohort_week": "2024-01-01", "cohort_size": 100, "activated": 50},
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_cohort_retention(findings, insights, metrics)

        assert not any(f.id == "analyst-cohort-001" for f in findings)
        assert metrics["avg_week2_retention"] > 0.20

    def test_low_activation_flagged(self):
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "signup_cohort_retention": [],
            "signup_cohort_activation": [
                {"cohort_week": "2024-01-01", "cohort_size": 100, "activated": 20},
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_cohort_retention(findings, insights, metrics)

        assert metrics["avg_activation_rate"] == 0.2
        assert any(f.id == "analyst-cohort-002" for f in findings)

    def test_skips_when_unavailable(self):
        from data_team.analyst.analyst import _scan_cohort_retention

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_cohort_retention(findings, insights, metrics)

        assert metrics["cohort_analysis_available"] is False


# ---------------------------------------------------------------------------
# ModelEngineer: warm score calibration
# ---------------------------------------------------------------------------


class TestModelEngineerCalibration:
    """Test warm score outcome correlation analysis."""

    def test_miscalibrated_scores_flagged(self):
        from data_team.model_engineer.model_engineer import _scan_warm_sco[RESEND_KEY_REDACTED]

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = [
            {"sco[RESEND_KEY_REDACTED]": "high", "total_intros": 50, "approved": 10},
            {"sco[RESEND_KEY_REDACTED]": "medium", "total_intros": 50, "approved": 30},
            {"sco[RESEND_KEY_REDACTED]": "low", "total_intros": 50, "approved": 40},
        ]

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_warm_sco[RESEND_KEY_REDACTED](findings, insights, metrics)

        assert metrics["warm_sco[RESEND_KEY_REDACTED]"] is False
        assert any(f.id == "model-009" for f in findings)
        # Band rates should be inverted
        assert (
            metrics["warm_sco[RESEND_KEY_REDACTED]"]["high"]
            < metrics["warm_sco[RESEND_KEY_REDACTED]"]["low"]
        )

    def test_well_calibrated_scores(self):
        from data_team.model_engineer.model_engineer import _scan_warm_sco[RESEND_KEY_REDACTED]

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = [
            {"sco[RESEND_KEY_REDACTED]": "high", "total_intros": 50, "approved": 40},
            {"sco[RESEND_KEY_REDACTED]": "medium", "total_intros": 50, "approved": 25},
            {"sco[RESEND_KEY_REDACTED]": "low", "total_intros": 50, "approved": 5},
        ]

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_warm_sco[RESEND_KEY_REDACTED](findings, insights, metrics)

        assert metrics["warm_sco[RESEND_KEY_REDACTED]"] is True
        assert not any(f.id == "model-009" for f in findings)

    def test_no_data_returns_early(self):
        from data_team.model_engineer.model_engineer import _scan_warm_sco[RESEND_KEY_REDACTED]

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = []

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_warm_sco[RESEND_KEY_REDACTED](findings, insights, metrics)

        assert metrics["warm_sco[RESEND_KEY_REDACTED]"] == 0
        assert len(findings) == 0

    def test_skips_when_unavailable(self):
        from data_team.model_engineer.model_engineer import _scan_warm_sco[RESEND_KEY_REDACTED]

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_warm_sco[RESEND_KEY_REDACTED](findings, insights, metrics)

        assert metrics["warm_sco[RESEND_KEY_REDACTED]"] is False


# ---------------------------------------------------------------------------
# ModelEngineer: A/B test analysis
# ---------------------------------------------------------------------------


class TestModelEngineerABTest:
    """Test cultural context effectiveness analysis."""

    def test_significant_style_difference(self):
        from data_team.model_engineer.model_engineer import _scan_ab_test_analysis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = [
            {"approach_style": "direct", "total_matches": 40, "positive_rate": 0.80},
            {"approach_style": "formal", "total_matches": 30, "positive_rate": 0.50},
        ]

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_ab_test_analysis(findings, insights, metrics)

        assert metrics["ab_test_variants_tested"] == 2
        assert metrics["ab_test_best_style"] == "direct"
        assert any(f.id == "model-010" for f in findings)

    def test_no_significant_difference(self):
        from data_team.model_engineer.model_engineer import _scan_ab_test_analysis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = [
            {"approach_style": "direct", "total_matches": 10, "positive_rate": 0.60},
            {"approach_style": "formal", "total_matches": 10, "positive_rate": 0.55},
        ]

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_ab_test_analysis(findings, insights, metrics)

        # Small gap (5%) + small sample — no finding
        assert not any(f.id == "model-010" for f in findings)

    def test_no_data(self):
        from data_team.model_engineer.model_engineer import _scan_ab_test_analysis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_sql.return_value = []

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _scan_ab_test_analysis(findings, insights, metrics)

        assert metrics["ab_test_variants_tested"] == 0


# ---------------------------------------------------------------------------
# DataLead: intelligence freshness
# ---------------------------------------------------------------------------


class TestDataLeadIntelFreshness:
    """Test intelligence freshness checking."""

    def test_stale_categories_flagged(self):
        from data_team.data_lead.data_lead import _check_intel_freshness

        findings: list[Finding] = []
        metrics: dict = {}

        mock_di = MagicMock()
        mock_di.check_freshness.return_value = {
            "marketplace_benchmarks": False,
            "job_market_data": False,
            "ml_research": True,
        }

        with patch(
            "data_team.data_lead.data_lead.DataIntelligence", return_value=mock_di
        ):
            _check_intel_freshness(findings, metrics)

        assert metrics["intel_categories_stale"] == 2
        assert any(f.id == "lead-intel-001" for f in findings)

    def test_all_fresh_no_finding(self):
        from data_team.data_lead.data_lead import _check_intel_freshness

        findings: list[Finding] = []
        metrics: dict = {}

        mock_di = MagicMock()
        mock_di.check_freshness.return_value = {
            "marketplace_benchmarks": True,
            "job_market_data": True,
        }

        with patch(
            "data_team.data_lead.data_lead.DataIntelligence", return_value=mock_di
        ):
            _check_intel_freshness(findings, metrics)

        assert metrics["intel_categories_stale"] == 0
        assert not any(f.id == "lead-intel-001" for f in findings)


# ---------------------------------------------------------------------------
# DataLead: live KPIs
# ---------------------------------------------------------------------------


class TestDataLeadLiveKPIs:
    """Test live KPI population from database."""

    def test_populates_kpi_values(self):
        from data_team.data_lead.data_lead import _populate_live_kpis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "activation_funnel": [
                {
                    "total_users": 100,
                    "uploaded": 50,
                    "searched": 30,
                    "requested_intro": 10,
                }
            ],
            "intro_approval_rate": [
                {"total_requests": 20, "approved": 12, "declined": 5, "pending": 3}
            ],
            "marketplace_health": [
                {
                    "total_listings": 500,
                    "active_listings": 300,
                    "companies_represented": 75,
                }
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _populate_live_kpis(findings, insights, metrics)

        assert metrics["live_kpis_available"] is True
        kpis = metrics["live_kpi_values"]
        assert kpis["activation_rate"] == 0.5
        assert kpis["upload_to_search_rate"] == 0.6
        assert kpis["search_to_intro_rate"] == round(10 / 30, 3)
        assert kpis["intro_approval_rate"] == 0.6
        assert kpis["marketplace_supply_coverage"] == 75

    def test_flags_below_threshold_kpis(self):
        from data_team.data_lead.data_lead import _populate_live_kpis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = True
        mock_qe.execute_template.side_effect = lambda name, params=None: {
            "activation_funnel": [
                {
                    "total_users": 100,
                    "uploaded": 10,
                    "searched": 2,
                    "requested_intro": 0,
                }
            ],
            "intro_approval_rate": [
                {"total_requests": 10, "approved": 1, "declined": 8, "pending": 1}
            ],
            "marketplace_health": [
                {"total_listings": 10, "active_listings": 5, "companies_represented": 3}
            ],
        }.get(name, [])

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _populate_live_kpis(findings, insights, metrics)

        # activation_rate = 0.1 < yellow threshold 0.25 → flagged
        kpi_findings = [f for f in findings if f.id.startswith("lead-kpi-")]
        assert len(kpi_findings) >= 1
        assert any("activation_rate" in f.id for f in kpi_findings)

    def test_skips_when_unavailable(self):
        from data_team.data_lead.data_lead import _populate_live_kpis

        findings: list[Finding] = []
        insights: list[Insight] = []
        metrics: dict = {}

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            _populate_live_kpis(findings, insights, metrics)

        assert metrics["live_kpis_available"] is False


# ---------------------------------------------------------------------------
# Integration: full scan() calls with mocked executor
# ---------------------------------------------------------------------------


class TestIntegrationScans:
    """Verify scan() functions include new steps and don't crash."""

    def test_pipeline_scan_includes_live_data_metrics(self):
        from data_team.pipeline.pipeline import scan

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            report = scan()

        assert report.agent == "pipeline"
        assert "live_db_available" in report.metrics
        assert report.metrics["live_db_available"] is False

    def test_analyst_scan_includes_anomaly_metrics(self):
        from data_team.analyst.analyst import scan

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            report = scan()

        assert report.agent == "analyst"
        assert "anomaly_detection_available" in report.metrics
        assert "cohort_analysis_available" in report.metrics

    def test_model_engineer_scan_includes_calibration_metrics(self):
        from data_team.model_engineer.model_engineer import scan

        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False

        with patch(
            "data_team.shared.query_executor.get_executor", return_value=mock_qe
        ):
            report = scan()

        assert report.agent == "model_engineer"
        assert "warm_sco[RESEND_KEY_REDACTED]" in report.metrics
        assert "ab_test_analysis_available" in report.metrics
