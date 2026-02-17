"""Tests for the product team agent system.

Tests cover:
  - ProductPrivacyGuard: PII rejection, research ethics
  - ProductTeamReport: creation, serialization, markdown, to_agent_report
  - UXLead scan: scan() returns report with accessibility findings
  - DesignLead scan: scan() returns report with design system findings
  - UserResearcher scan: scan() returns report
  - ProductManager scan: scan() returns report
  - ProductLead brief: daily/weekly brief generation
  - ProductLearningState: finding recording, patterns, health trajectory
  - ProductIntelligence: categories, add/get, urgency, adoption
  - CoS integration: config activation, business outcomes mapping
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# TestProductPrivacyGuard
# ---------------------------------------------------------------------------


class TestProductPrivacyGuard:
    """Privacy guard must reject PII in research outputs."""

    def _get_guard(self):
        from product_team.shared.privacy_guard import ProductPrivacyGuard
        return ProductPrivacyGuard()

    def _get_violation(self):
        from product_team.shared.privacy_guard import PrivacyViolation
        return PrivacyViolation

    def test_rejects_email_in_finding(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_finding("User john@example.com reported an issue")
        assert exc_info.value.privy_category == "pii_leak"

    def test_rejects_phone_in_finding(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_finding("Contact number: 555-123-4567")
        assert exc_info.value.privy_category == "pii_leak"

    def test_rejects_linkedin_url_in_finding(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_finding("Profile at linkedin.com/in/johndoe")
        assert exc_info.value.privy_category == "pii_leak"

    def test_accepts_clean_finding(self):
        guard = self._get_guard()
        assert guard.validate_finding("UX score is 75/100 across 15 pages") is True

    def test_rejects_forbidden_action(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation):
            guard.validate_research_action("scrape_user_data from contacts table")

    def test_accepts_valid_action(self):
        guard = self._get_guard()
        assert guard.validate_research_action("analyze page accessibility") is True

    def test_rejects_pii_columns_in_output(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation):
            guard.validate_output_columns(["id", "email", "score"])

    def test_accepts_clean_columns(self):
        guard = self._get_guard()
        assert guard.validate_output_columns(["id", "score", "category"]) is True

    def test_audit_log_tracks_validations(self):
        guard = self._get_guard()
        guard.validate_finding("Clean text about UX")
        assert len(guard.get_audit_log()) >= 1


# ---------------------------------------------------------------------------
# TestProductTeamReport
# ---------------------------------------------------------------------------


class TestProductTeamReport:
    """ProductTeamReport must serialize, render markdown, and convert to AgentReport."""

    def test_create_empty_report(self):
        from product_team.shared.report import ProductTeamReport
        report = ProductTeamReport(agent="test_agent")
        assert report.agent == "test_agent"
        assert report.findings == []
        assert report.scan_duration_seconds == 0

    def test_create_report_with_findings(self):
        from agents.shared.report import Finding
        from product_team.shared.report import ProductTeamReport
        finding = Finding(
            id="test-001",
            severity="medium",
            category="ux_quality",
            title="Missing loading state",
            detail="No spinner in Dashboard",
        )
        report = ProductTeamReport(
            agent="ux_lead",
            scan_duration_seconds=1.5,
            findings=[finding],
        )
        assert len(report.findings) == 1
        assert report.scan_duration_seconds == 1.5

    def test_serialize_deserialize(self):
        from agents.shared.report import Finding
        from product_team.shared.report import ProductTeamReport
        finding = Finding(
            id="test-001",
            severity="medium",
            category="ux_quality",
            title="Test finding",
            detail="Test detail",
        )
        report = ProductTeamReport(
            agent="ux_lead",
            scan_duration_seconds=1.0,
            findings=[finding],
            metrics={"score": 85},
        )
        json_str = report.serialize()
        data = json.loads(json_str)
        restored = ProductTeamReport.from_dict(data)
        assert restored.agent == "ux_lead"
        assert len(restored.findings) == 1
        assert restored.metrics["score"] == 85

    def test_to_markdown(self):
        from agents.shared.report import Finding
        from product_team.shared.report import ProductTeamReport
        finding = Finding(
            id="test-001",
            severity="high",
            category="ux_quality",
            title="Accessibility issue",
            detail="Missing aria labels",
            recommendation="Add aria-label attributes",
        )
        report = ProductTeamReport(
            agent="ux_lead",
            scan_duration_seconds=0.5,
            findings=[finding],
        )
        md = report.to_markdown()
        assert "ux_lead Report" in md
        assert "Accessibility issue" in md

    def test_to_agent_report(self):
        from agents.shared.report import AgentReport, Finding
        from product_team.shared.report import ProductTeamReport
        finding = Finding(
            id="test-001",
            severity="medium",
            category="ux_quality",
            title="Test",
            detail="Detail",
        )
        report = ProductTeamReport(
            agent="ux_lead",
            scan_duration_seconds=1.0,
            findings=[finding],
            metrics={"score": 85},
            learning_updates=["Scanned 10 files"],
        )
        ar = report.to_agent_report()
        assert isinstance(ar, AgentReport)
        assert ar.agent == "ux_lead"
        assert len(ar.findings) == 1
        assert ar.scan_duration_seconds == 1.0
        assert ar.metrics["score"] == 85


# ---------------------------------------------------------------------------
# TestUXLeadScan
# ---------------------------------------------------------------------------


class TestUXLeadScan:
    """UXLead scan() should return a ProductTeamReport with findings."""

    def test_scan_returns_report(self):
        from product_team.ux_lead.ux_lead import scan
        report = scan()
        assert report.agent == "ux_lead"
        assert isinstance(report.scan_duration_seconds, float)
        assert report.scan_duration_seconds >= 0
        assert isinstance(report.metrics, dict)
        assert "total_jsx_files" in report.metrics

    def test_scan_finds_jsx_files(self):
        from product_team.ux_lead.ux_lead import scan
        report = scan()
        # We know frontend has JSX files
        assert report.metrics["total_jsx_files"] > 0

    def test_scan_has_ux_health_score(self):
        from product_team.ux_lead.ux_lead import scan
        report = scan()
        assert "ux_health_score" in report.metrics


# ---------------------------------------------------------------------------
# TestDesignLeadScan
# ---------------------------------------------------------------------------


class TestDesignLeadScan:
    """DesignLead scan() should return a ProductTeamReport with design findings."""

    def test_scan_returns_report(self):
        from product_team.design_lead.design_lead import scan
        report = scan()
        assert report.agent == "design_lead"
        assert isinstance(report.scan_duration_seconds, float)
        assert isinstance(report.metrics, dict)
        assert "total_jsx_files" in report.metrics

    def test_scan_has_design_system_score(self):
        from product_team.design_lead.design_lead import scan
        report = scan()
        assert "design_system_score" in report.metrics

    def test_scan_checks_colors(self):
        from product_team.design_lead.design_lead import scan
        report = scan()
        assert "unique_hardcoded_colors" in report.metrics


# ---------------------------------------------------------------------------
# TestUserResearcherScan
# ---------------------------------------------------------------------------


class TestUserResearcherScan:
    """UserResearcher scan() should return a ProductTeamReport."""

    def test_scan_returns_report(self):
        from product_team.user_researcher.user_researcher import scan
        report = scan()
        assert report.agent == "user_researcher"
        assert isinstance(report.scan_duration_seconds, float)

    def test_scan_maps_journeys(self):
        from product_team.user_researcher.user_researcher import scan
        report = scan()
        assert "pages_found" in report.metrics or "total_page_files" in report.metrics

    def test_scan_produces_insights(self):
        from product_team.user_researcher.user_researcher import scan
        report = scan()
        # Should produce at least persona insights + source catalog
        assert len(report.product_insights) >= 1


# ---------------------------------------------------------------------------
# TestProductManagerScan
# ---------------------------------------------------------------------------


class TestProductManagerScan:
    """ProductManager scan() should return a ProductTeamReport."""

    def test_scan_returns_report(self):
        from product_team.product_manager.product_manager import scan
        report = scan()
        assert report.agent == "product_manager"
        assert isinstance(report.scan_duration_seconds, float)

    def test_scan_maps_endpoints(self):
        from product_team.product_manager.product_manager import scan
        report = scan()
        assert "total_api_endpoints" in report.metrics

    def test_scan_has_featu[RESEND_KEY_REDACTED](self):
        from product_team.product_manager.product_manager import scan
        report = scan()
        assert "featu[RESEND_KEY_REDACTED]" in report.metrics


# ---------------------------------------------------------------------------
# TestProductLeadBrief
# ---------------------------------------------------------------------------


class TestProductLeadBrief:
    """ProductLead should generate daily/weekly briefs."""

    def test_daily_brief_no_reports(self):
        from product_team.product_lead.product_lead import generate_daily_brief
        brief = generate_daily_brief(reports=[])
        assert "Product Team Daily Brief" in brief
        assert "No agent reports available" in brief

    def test_daily_brief_with_reports(self):
        from agents.shared.report import Finding
        from product_team.shared.report import ProductTeamReport
        from product_team.product_lead.product_lead import generate_daily_brief

        report = ProductTeamReport(
            agent="ux_lead",
            scan_duration_seconds=0.5,
            findings=[Finding(
                id="test-001", severity="medium", category="ux_quality",
                title="Test UX finding", detail="Detail",
            )],
            metrics={"ux_health_score": 75},
        )
        brief = generate_daily_brief(reports=[report])
        assert "Product Team Daily Brief" in brief
        assert "Product Scorecard" in brief

    def test_weekly_report_no_reports(self):
        from product_team.product_lead.product_lead import generate_weekly_report
        report = generate_weekly_report(reports=[])
        assert "Product Team Weekly Report" in report
        assert "No agent reports available" in report

    def test_weekly_report_with_reports(self):
        from agents.shared.report import Finding
        from product_team.shared.report import ProductTeamReport
        from product_team.product_lead.product_lead import generate_weekly_report

        report = ProductTeamReport(
            agent="design_lead",
            scan_duration_seconds=0.3,
            findings=[Finding(
                id="ds-001", severity="low", category="design_system",
                title="Test design finding", detail="Detail",
            )],
            metrics={"design_system_score": 90},
        )
        result = generate_weekly_report(reports=[report])
        assert "Product Team Weekly Report" in result
        assert "Product Readiness Scorecard" in result

    def test_scan_returns_report(self):
        from product_team.product_lead.product_lead import scan
        report = scan()
        assert report.agent == "product_lead"
        assert isinstance(report.scan_duration_seconds, float)


# ---------------------------------------------------------------------------
# TestProductLearningState
# ---------------------------------------------------------------------------


class TestProductLearningState:
    """ProductLearningState should track findings, patterns, health."""

    def test_record_finding(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")
        ls.record_finding({
            "id": "f-001",
            "severity": "medium",
            "category": "ux_quality",
            "title": "Test finding",
            "file": "test.jsx",
        })
        assert len(ls.state["finding_history"]) == 1
        assert ls.state["finding_history"][0]["category"] == "ux_quality"

    def test_recurring_pattern_detection(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")

        # Record 5+ findings to trigger auto-escalation
        for i in range(6):
            ls.record_finding({
                "id": f"f-{i:03d}",
                "severity": "medium",
                "category": "accessibility",
                "title": f"Finding {i}",
                "file": "test.jsx",
            })

        pattern = ls.detect_recurring_pattern("accessibility", "test.jsx")
        assert pattern["count"] >= 5
        assert pattern["auto_escalated"] is True

    def test_health_trajectory(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")

        # Record 2 health snapshots
        ls.record_health_snapshot(60.0, {"medium": 3})
        ls.record_health_snapshot(80.0, {"medium": 1})

        trajectory = ls.get_health_trajectory()
        assert trajectory in ("improving", "stable", "degrading", "insufficient_data")

    def test_meta_learning_report(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")
        ls.record_scan({"score": 75})
        report = ls.generate_meta_learning_report()
        assert report["agent"] == "test_agent"
        assert report["total_scans"] == 1

    def test_severity_calibration(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")
        ls.record_severity_calibration("medium")
        ls.record_severity_calibration("medium")
        ls.record_severity_calibration("high")

        cal = ls.get_severity_calibration()
        assert cal["medium"]["total"] == 2
        assert cal["high"]["total"] == 1

    def test_tool_accuracy(self, tmp_path, monkeypatch):
        import product_team.shared.learning as learning_mod
        monkeypatch.setattr(learning_mod, "PRODUCT_TEAM_DIR", tmp_path)

        from product_team.shared.learning import ProductLearningState
        ls = ProductLearningState("test_agent")
        ls.record_tool_accuracy("regex_scanner", "f-001", confirmed=True)
        ls.record_tool_accuracy("regex_scanner", "f-002", confirmed=False)

        reliability = ls.get_tool_reliability()
        assert "regex_scanner" in reliability
        assert reliability["regex_scanner"] == 0.5


# ---------------------------------------------------------------------------
# TestProductIntelligence
# ---------------------------------------------------------------------------


class TestProductIntelligence:
    """ProductIntelligence should track and manage intel items."""

    def test_categories_defined(self):
        from product_team.shared.intelligence import PRODUCT_INTEL_CATEGORIES
        assert len(PRODUCT_INTEL_CATEGORIES) == 12

    def test_add_and_get_item(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelItem, ProductIntelligence
        pi = ProductIntelligence()
        item = ProductIntelItem(
            category="user_forums",
            title="Reddit thread on referral frustrations",
            summary="Users complain about cold applications",
            severity="medium",
            relevant_agents=["user_researcher"],
        )
        pi.add_item(item)

        items = pi.get_all()
        assert len(items) >= 1
        assert items[0].category == "user_forums"

    def test_get_urgent(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelItem, ProductIntelligence
        pi = ProductIntelligence()
        pi.add_item(ProductIntelItem(category="c1", title="Low", severity="low"))
        pi.add_item(ProductIntelItem(category="c2", title="High", severity="high"))

        urgent = pi.get_urgent()
        assert len(urgent) == 1
        assert urgent[0].severity == "high"

    def test_mark_adopted(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelItem, ProductIntelligence
        pi = ProductIntelligence()
        item = ProductIntelItem(id="test-id", category="c1", title="Test")
        pi.add_item(item)

        assert pi.mark_adopted("test-id", "user_researcher") is True
        unadopted = pi.get_unadopted()
        assert all(u.id != "test-id" for u in unadopted)

    def test_freshness_check(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelligence
        pi = ProductIntelligence()
        freshness = pi.check_freshness()
        # All should be stale (no cache entries)
        assert all(not v for v in freshness.values())

    def test_research_agenda(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelligence
        pi = ProductIntelligence()
        agenda = pi.generate_research_agenda()
        assert len(agenda) > 0
        assert all("category" in item for item in agenda)

    def test_intel_report(self, tmp_path, monkeypatch):
        import product_team.shared.intelligence as intel_mod
        monkeypatch.setattr(intel_mod, "INTEL_CACHE", tmp_path / "cache.json")

        from product_team.shared.intelligence import ProductIntelligence
        pi = ProductIntelligence()
        report = pi.generate_intel_report()
        assert "total_items" in report
        assert report["categories_total"] == 12


# ---------------------------------------------------------------------------
# TestCosIntegration
# ---------------------------------------------------------------------------


class TestCosIntegration:
    """CoS config and business outcomes should include product team."""

    def test_product_team_active_in_config(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG
        product = COS_CONFIG["teams"]["product"]
        assert product["active"] is True
        assert product["report_dir"] == "product_team/reports"

    def test_product_budget_in_config(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG
        assert "product_team_daily_max_tokens" in COS_CONFIG["cost_budget"]

    def test_product_categories_in_outcome_map(self):
        from agents.shared.business_outcomes import CATEGORY_OUTCOME_MAP
        product_categories = ["ux_quality", "design_system", "featu[RESEND_KEY_REDACTED]",
                              "user_research", "product_strategy"]
        for cat in product_categories:
            assert cat in CATEGORY_OUTCOME_MAP, f"Missing category: {cat}"

    def test_product_impact_templates(self):
        from agents.shared.business_outcomes import get_business_impact
        impact = get_business_impact("ux_quality", "high")
        assert "UX" in impact or "friction" in impact

    def test_product_team_in_cos_learning(self):
        from agents.chief_of_staff.cos_learning import _default_state
        state = _default_state()
        assert "product" in state["team_reliability"]

    def test_product_outcomes_score(self):
        from agents.shared.business_outcomes import get_aligned_outcomes, sco[RESEND_KEY_REDACTED]
        outcomes = get_aligned_outcomes("ux_quality")
        assert len(outcomes) >= 1
        score = sco[RESEND_KEY_REDACTED](outcomes)
        assert 0.0 <= score <= 1.0
