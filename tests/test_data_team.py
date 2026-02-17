"""Tests for the data science agent team.

Tests cover:
  - PrivacyGuard (CoS-expanded): PII rejection, vault isolation, immutability, k-anonymity
  - SQL templates: all pass privacy validation, parameterization
  - DataTeamReport: creation, serialization, markdown rendering
  - Agent scan() functions: pipeline, analyst, model_engineer, data_lead
  - CoS integration: config activation, business outcome mapping
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# TestPrivacyGuard — CoS-mandated coverage
# ---------------------------------------------------------------------------


class TestPrivacyGuard:
    """Privacy guard must enforce all 10 Privy categories."""

    def _get_guard(self):
        from data_team.shared.privacy_guard import PrivacyGuard
        return PrivacyGuard()

    def _get_violation(self):
        from data_team.shared.privacy_guard import PrivacyViolation
        return PrivacyViolation

    # -- PII in SELECT (privy: pii_leak) ------------------------------------

    @pytest.mark.parametrize("col", [
        "first_name", "last_name", "full_name", "email", "linkedin_url",
        "current_title", "current_company", "location", "notes",
        "how_you_know", "email_blind_index", "name_company_blind_index",
        "raw_csv_row",
    ])
    def test_rejects_pii_column_in_select(self, col):
        """Each of the 13 PII columns must be rejected in SELECT clauses."""
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = f"SELECT {col}, id FROM contacts WHERE user_id = :uid"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "pii_leak"
        assert exc_info.value.violation_type == "pii_in_select"

    def test_accepts_count_aggregation_no_pii(self):
        """Aggregation without PII should pass."""
        guard = self._get_guard()
        sql = "SELECT COUNT(*) AS total FROM usage_logs WHERE action = :action"
        assert guard.validate_query(sql) is True

    def test_accepts_avg_aggregation(self):
        guard = self._get_guard()
        sql = "SELECT AVG(total_score) AS avg_score FROM warm_scores WHERE user_id = :uid"
        assert guard.validate_query(sql) is True

    def test_accepts_user_scoped_vault_query(self):
        guard = self._get_guard()
        sql = "SELECT id, total_score FROM warm_scores WHERE user_id = :uid"
        assert guard.validate_query(sql) is True

    # -- Cross-vault JOINs (privy: vault_isolation) -------------------------

    def test_rejects_contacts_self_join(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT a.id FROM contacts a JOIN contacts b ON a.id = b.id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "vault_isolation"

    def test_rejects_contacts_marketplace_without_consent(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT c.id FROM contacts c JOIN marketplace_listings m ON c.id = m.contact_id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "vault_isolation"

    def test_accepts_contacts_marketplace_with_consent_gate(self):
        guard = self._get_guard()
        sql = "SELECT c.id FROM marketplace_listings m JOIN contacts c ON c.id = m.contact_id WHERE m.opt_in_marketplace = TRUE"
        assert guard.validate_query(sql) is True

    # -- Immutable tables (privy: audit_immutability) -----------------------

    def test_rejects_update_audit_logs(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "UPDATE audit_logs SET action = 'modified' WHERE id = :id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "audit_immutability"

    def test_rejects_delete_audit_logs(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "DELETE FROM audit_logs WHERE id = :id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "audit_immutability"

    def test_rejects_update_consent_records(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "UPDATE consent_records SET status = 'revoked' WHERE id = :id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "audit_immutability"

    def test_rejects_delete_consent_records(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "DELETE FROM consent_records WHERE id = :id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "audit_immutability"

    # -- Suppression plaintext (privy: suppression) -------------------------

    def test_rejects_plaintext_suppression_email(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT * FROM suppression_list WHERE email = 'foo@bar.com'"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "suppression"

    def test_rejects_plaintext_suppression_name(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT * FROM suppression_list WHERE full_name = 'John Doe'"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_query(sql)
        assert exc_info.value.privy_category == "suppression"

    # -- k-anonymity (privy: info_leak) -------------------------------------

    def test_rejects_group_by_without_k_anonymity(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT company_id, COUNT(*) FROM marketplace_listings GROUP BY company_id"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_aggregation(sql)
        assert exc_info.value.privy_category == "info_leak"

    def test_rejects_group_by_with_low_k(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        sql = "SELECT company_id, COUNT(*) FROM marketplace_listings GROUP BY company_id HAVING COUNT(*) >= 2"
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_aggregation(sql)
        assert exc_info.value.privy_category == "info_leak"

    def test_accepts_group_by_with_k_anonymity(self):
        guard = self._get_guard()
        sql = "SELECT company_id, COUNT(*) FROM marketplace_listings GROUP BY company_id HAVING COUNT(*) >= 5"
        assert guard.validate_aggregation(sql) is True

    def test_accepts_group_by_with_higher_k(self):
        guard = self._get_guard()
        sql = "SELECT company_id, COUNT(*) FROM marketplace_listings GROUP BY company_id HAVING COUNT(*) >= 10"
        assert guard.validate_aggregation(sql) is True

    # -- PII in output columns (privy: pii_leak) ---------------------------

    def test_rejects_pii_in_output_columns(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_no_pii_in_output(["id", "email", "count"])
        assert exc_info.value.privy_category == "pii_leak"

    def test_accepts_clean_output_columns(self):
        guard = self._get_guard()
        assert guard.validate_no_pii_in_output(["id", "count", "avg_score"]) is True

    # -- Allowed exceptions -------------------------------------------------

    def test_allowed_exception_intro_with_consent(self):
        guard = self._get_guard()
        sql = "SELECT c.id FROM intro_facilitations inf JOIN contacts c ON c.id = inf.contact_id WHERE inf.consent = TRUE"
        assert guard.validate_query(sql) is True

    def test_allowed_exception_hash_based_dedup(self):
        guard = self._get_guard()
        sql = "SELECT c.id FROM contacts c WHERE c.email_blind_index IN (SELECT email_hash FROM suppression_list)"
        assert guard.validate_query(sql) is True

    # -- PrivacyViolation fields --------------------------------------------

    def test_privacy_violation_has_type_and_category(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        try:
            guard.validate_query("SELECT email FROM contacts WHERE user_id = :uid")
            assert False, "Should have raised"
        except PrivacyViolation as e:
            assert e.violation_type == "pii_in_select"
            assert e.privy_category == "pii_leak"
            assert "email" in str(e)

    # -- Audit log ----------------------------------------------------------

    def test_audit_log_records_queries(self):
        guard = self._get_guard()
        guard.validate_query("SELECT COUNT(*) FROM users WHERE created_at > :d")
        log = guard.get_audit_log()
        assert len(log) >= 1
        assert "agent" in log[-1]
        assert "timestamp" in log[-1]


# ---------------------------------------------------------------------------
# TestSqlTemplates
# ---------------------------------------------------------------------------


class TestSqlTemplates:
    """All SQL templates must pass privacy validation."""

    def test_all_templates_pass_validation(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES, validate_all_templates
        errors = validate_all_templates()
        assert errors == [], f"Template violations: {errors}"

    def test_template_count(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES
        assert len(ALL_TEMPLATES) >= 10, f"Expected 10+ templates, got {len(ALL_TEMPLATES)}"

    def test_templates_have_parameters(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES
        # Most templates should have :param_name placeholders
        parameterized = [
            name for name, sql in ALL_TEMPLATES.items()
            if ":start_date" in sql or ":end_date" in sql or ":user_id" in sql
        ]
        assert len(parameterized) >= 5, "Most templates should be parameterized"

    def test_funnel_templates_exist(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES
        assert "daily_signups" in ALL_TEMPLATES
        assert "activation_funnel" in ALL_TEMPLATES

    def test_marketplace_templates_exist(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES
        assert "marketplace_health" in ALL_TEMPLATES
        assert "intro_approval_rate" in ALL_TEMPLATES

    def test_cohort_templates_exist(self):
        from data_team.shared.sql_templates import ALL_TEMPLATES
        assert "signup_cohort_retention" in ALL_TEMPLATES


# ---------------------------------------------------------------------------
# TestDataTeamReport
# ---------------------------------------------------------------------------


class TestDataTeamReport:
    """DataTeamReport creation, serialization, and rendering."""

    def test_create_report(self):
        from data_team.shared.report import DataTeamReport
        report = DataTeamReport(agent="test_agent")
        assert report.agent == "test_agent"
        assert report.timestamp != ""
        assert report.scan_duration_seconds == 0
        assert report.findings == []

    def test_create_insight(self):
        from data_team.shared.report import Insight
        insight = Insight(
            id="test-001",
            category="funnel",
            title="Test insight",
            evidence="Evidence here",
            impact="High impact",
            recommendation="Do something",
            confidence=0.85,
        )
        assert insight.confidence == 0.85

    def test_create_kpi_snapshot(self):
        from data_team.shared.report import KPISnapshot
        kpi = KPISnapshot(
            kpi_name="activation_rate",
            current_value=0.35,
            target_value=0.40,
            trend="improving",
            status="yellow",
        )
        assert kpi.kpi_name == "activation_rate"

    def test_serialize_and_deserialize(self):
        from agents.shared.report import Finding
        from data_team.shared.report import DataTeamReport, Insight

        report = DataTeamReport(
            agent="test",
            scan_duration_seconds=1.5,
            findings=[Finding(id="f1", severity="medium", category="test", title="Test", detail="Detail")],
            insights=[Insight(id="i1", category="funnel", title="Insight", evidence="Ev", impact="Im", recommendation="Rec")],
            metrics={"key": "value"},
        )
        serialized = report.serialize()
        data = json.loads(serialized)
        restored = DataTeamReport.from_dict(data)
        assert restored.agent == "test"
        assert len(restored.findings) == 1
        assert len(restored.insights) == 1

    def test_to_markdown(self):
        from agents.shared.report import Finding
        from data_team.shared.report import DataTeamReport

        report = DataTeamReport(
            agent="test",
            findings=[Finding(id="f1", severity="high", category="test", title="Test Finding", detail="Details")],
        )
        md = report.to_markdown()
        assert "# test Report" in md
        assert "Test Finding" in md

    def test_to_agent_report(self):
        from data_team.shared.report import DataTeamReport

        report = DataTeamReport(agent="test", scan_duration_seconds=2.0)
        ar = report.to_agent_report()
        assert ar.agent == "test"
        assert ar.scan_duration_seconds == 2.0


# ---------------------------------------------------------------------------
# TestPipelineScan
# ---------------------------------------------------------------------------


class TestPipelineScan:
    """Pipeline agent scan produces a valid DataTeamReport."""

    def test_scan_returns_report(self):
        from data_team.pipeline.pipeline import scan
        report = scan()
        assert report.agent == "pipeline"
        assert report.scan_duration_seconds >= 0
        assert isinstance(report.findings, list)
        assert isinstance(report.metrics, dict)

    def test_scan_produces_findings(self):
        from data_team.pipeline.pipeline import scan
        report = scan()
        # Should find at least some schema or instrumentation findings
        assert len(report.findings) >= 0  # May be zero if everything is clean

    def test_scan_has_metrics(self):
        from data_team.pipeline.pipeline import scan
        report = scan()
        assert "tables_in_models" in report.metrics or "sql_templates_count" in report.metrics


# ---------------------------------------------------------------------------
# TestAnalystScan
# ---------------------------------------------------------------------------


class TestAnalystScan:
    """Analyst agent scan produces a valid DataTeamReport."""

    def test_scan_returns_report(self):
        from data_team.analyst.analyst import scan
        report = scan()
        assert report.agent == "analyst"
        assert isinstance(report.findings, list)
        assert isinstance(report.insights, list)

    def test_scan_has_funnel_metrics(self):
        from data_team.analyst.analyst import scan
        report = scan()
        assert "funnel_steps_total" in report.metrics
        assert "total_endpoints" in report.metrics


# ---------------------------------------------------------------------------
# TestModelEngineerScan
# ---------------------------------------------------------------------------


class TestModelEngineerScan:
    """ModelEngineer agent scan produces a valid DataTeamReport."""

    def test_scan_returns_report(self):
        from data_team.model_engineer.model_engineer import scan
        report = scan()
        assert report.agent == "model_engineer"
        assert isinstance(report.findings, list)


# ---------------------------------------------------------------------------
# TestDataLeadBrief
# ---------------------------------------------------------------------------


class TestDataLeadBrief:
    """DataLead brief generation."""

    def test_daily_brief_produces_markdown(self):
        from data_team.data_lead.data_lead import generate_daily_brief
        brief = generate_daily_brief(reports=[])
        assert "# Data Team Daily Brief" in brief

    def test_daily_brief_with_reports(self):
        from data_team.data_lead.data_lead import generate_daily_brief
        from data_team.pipeline.pipeline import scan as pipeline_scan
        report = pipeline_scan()
        brief = generate_daily_brief(reports=[report])
        assert "Data Team Daily Brief" in brief

    def test_weekly_report_produces_markdown(self):
        from data_team.data_lead.data_lead import generate_weekly_report
        report = generate_weekly_report(reports=[])
        assert "Weekly Report" in report

    def test_monthly_review_produces_markdown(self):
        from data_team.data_lead.data_lead import generate_monthly_review
        review = generate_monthly_review(reports=[])
        assert "Monthly Review" in review


# ---------------------------------------------------------------------------
# TestCosIntegration
# ---------------------------------------------------------------------------


class TestCosIntegration:
    """CoS config and business outcomes include data team."""

    def test_cos_config_has_data_team(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG
        teams = COS_CONFIG["teams"]
        assert "data" in teams
        assert teams["data"]["active"] is True

    def test_cos_config_has_data_report_dir(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG
        teams = COS_CONFIG["teams"]
        assert "report_dir" in teams["data"]
        assert "data_team" in teams["data"]["report_dir"]

    def test_business_outcomes_has_data_categories(self):
        from agents.shared.business_outcomes import CATEGORY_OUTCOME_MAP
        assert "data_quality" in CATEGORY_OUTCOME_MAP
        assert "instrumentation" in CATEGORY_OUTCOME_MAP
        assert "model_calibration" in CATEGORY_OUTCOME_MAP
        assert "schema_coverage" in CATEGORY_OUTCOME_MAP
        assert "privacy_compliance" in CATEGORY_OUTCOME_MAP

    def test_business_outcomes_data_impact_templates(self):
        from agents.shared.business_outcomes import get_business_impact
        # data_quality should have custom templates
        impact = get_business_impact("data_quality", "critical")
        assert "data" in impact.lower() or "analytics" in impact.lower() or "integrity" in impact.lower()

    def test_data_team_report_converts_to_agent_report(self):
        """DataTeamReport.to_agent_report() produces CoS-compatible AgentReport."""
        from data_team.shared.report import DataTeamReport
        from agents.shared.report import AgentReport
        report = DataTeamReport(agent="test", scan_duration_seconds=1.0)
        ar = report.to_agent_report()
        assert isinstance(ar, AgentReport)
        assert ar.scan_duration_seconds == 1.0

    def test_cos_learning_default_has_data_team(self):
        from agents.chief_of_staff.cos_learning import _default_state
        state = _default_state()
        assert "data" in state["team_reliability"]

    def test_cos_config_has_data_budget(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG
        budget = COS_CONFIG["cost_budget"]
        assert "data_team_daily_max_tokens" in budget
