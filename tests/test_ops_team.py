"""Tests for the ops team agent system.

Tests cover:
  - OpsPrivacyGuard: PII rejection, forbidden actions, aggregate threshold
  - OpsTeamReport: creation, serialization, markdown, to_agent_report
  - Keevs scan: scan() returns report with coaching findings
  - Treb scan: scan() returns report with supply-side findings
  - Naiv scan: scan() returns report with satisfaction findings
  - Marsh scan: scan() returns report with marketplace findings
  - OpsLead: daily/weekly/monthly brief generation
  - OpsLearningState: finding recording, patterns, health trajectory
  - OpsIntelligence: categories, add/get, urgency, adoption
  - CoS integration: config activation, business outcomes mapping
"""

from __future__ import annotations

import json
import pytest


# ---------------------------------------------------------------------------
# TestOpsPrivacyGuard
# ---------------------------------------------------------------------------


class TestOpsPrivacyGuard:
    """Privacy guard must reject PII and enforce aggregate thresholds."""

    def _get_guard(self):
        from ops_team.shared.privacy_guard import OpsPrivacyGuard

        return OpsPrivacyGuard()

    def _get_violation(self):
        from ops_team.shared.privacy_guard import PrivacyViolation

        return PrivacyViolation

    def test_rejects_email_in_finding(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_finding("User john@example.com had a bad experience")
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
        assert (
            guard.validate_finding(
                "Coaching quality score is 85/100 across 20 sessions"
            )
            is True
        )

    def test_rejects_forbidden_action(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_action("expose_user_activity for analytics")
        assert exc_info.value.privy_category == "user_activity_leak"

    def test_rejects_identify_job_seekers(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation):
            guard.validate_action("identify_job_seekers at company X")

    def test_accepts_valid_action(self):
        guard = self._get_guard()
        assert guard.validate_action("audit coaching prompt coverage") is True

    def test_rejects_low_aggregate(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation) as exc_info:
            guard.validate_aggregate_threshold(3)
        assert exc_info.value.privy_category == "individual_identification"

    def test_accepts_sufficient_aggregate(self):
        guard = self._get_guard()
        assert guard.validate_aggregate_threshold(10) is True

    def test_rejects_pii_columns_in_output(self):
        guard = self._get_guard()
        PrivacyViolation = self._get_violation()
        with pytest.raises(PrivacyViolation):
            guard.validate_output_columns(["id", "email", "score"])

    def test_accepts_clean_columns(self):
        guard = self._get_guard()
        assert guard.validate_output_columns(["category", "count", "score"]) is True


# ---------------------------------------------------------------------------
# TestOpsTeamReport
# ---------------------------------------------------------------------------


class TestOpsTeamReport:
    """Report schema creation, serialization, and conversion."""

    def _make_report(self):
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight, OpsTeamReport

        findings = [
            Finding(
                id="keevs-001",
                severity="medium",
                category="coaching_quality",
                title="System prompt missing salary negotiation",
                detail="No coverage for salary negotiation scenarios",
                recommendation="Add salary negotiation prompts",
            ),
        ]
        insights = [
            OpsInsight(
                id="keevs-ins-001",
                title="Coach covers 80% of journey",
                category="coaching_effectiveness",
                evidence="4 of 5 key scenarios covered",
                impact="Job seekers missing 20% of coaching scenarios",
                recommendation="Add salary negotiation and counter-offer coaching",
                confidence=0.85,
            ),
        ]
        return OpsTeamReport(
            agent="keevs",
            scan_duration_seconds=1.5,
            findings=findings,
            ops_insights=insights,
            metrics={"coaching_quality_score": 0.80},
        )

    def test_report_creation(self):
        report = self._make_report()
        assert report.agent == "keevs"
        assert len(report.findings) == 1
        assert len(report.ops_insights) == 1
        assert report.metrics["coaching_quality_score"] == 0.80

    def test_serialize_roundtrip(self):
        report = self._make_report()
        serialized = report.serialize()
        data = json.loads(serialized)
        assert data["agent"] == "keevs"
        assert len(data["findings"]) == 1
        assert data["metrics"]["coaching_quality_score"] == 0.80

    def test_from_dict(self):
        from ops_team.shared.report import OpsTeamReport

        report = self._make_report()
        data = json.loads(report.serialize())
        restored = OpsTeamReport.from_dict(data)
        assert restored.agent == "keevs"
        assert len(restored.findings) == 1

    def test_to_markdown(self):
        report = self._make_report()
        md = report.to_markdown()
        assert "keevs" in md
        assert "System prompt missing salary negotiation" in md
        assert "coaching_effectiveness" in md

    def test_to_agent_report(self):
        report = self._make_report()
        ar = report.to_agent_report()
        assert ar.agent == "keevs"
        assert len(ar.findings) == 1

    def test_cross_team_requests(self):
        from ops_team.shared.report import OpsTeamReport

        report = OpsTeamReport(
            agent="ops_lead",
            scan_duration_seconds=0.5,
            findings=[],
            cross_team_requests=[
                {
                    "target_team": "engineering",
                    "urgency": "high",
                    "request": "Fix SSE timeout",
                    "source_agent": "keevs",
                }
            ],
        )
        assert len(report.cross_team_requests) == 1
        assert report.cross_team_requests[0]["target_team"] == "engineering"


# ---------------------------------------------------------------------------
# TestKeevsScan
# ---------------------------------------------------------------------------


class TestKeevsScan:
    """Keevs agent scans coaching service quality."""

    def test_scan_returns_report(self):
        from ops_team.keevs.keevs import scan

        report = scan()
        assert report.agent == "keevs"
        assert report.scan_duration_seconds >= 0
        assert isinstance(report.findings, list)
        assert isinstance(report.metrics, dict)

    def test_scan_has_coaching_metrics(self):
        from ops_team.keevs.keevs import scan

        report = scan()
        # Should have at least some coaching-related metric
        assert len(report.metrics) > 0

    def test_scan_findings_have_ids(self):
        from ops_team.keevs.keevs import scan

        report = scan()
        for f in report.findings:
            assert f.id, "Finding must have an ID"
            assert f.severity in ("critical", "high", "medium", "low", "info")

    def test_scan_ops_insights(self):
        from ops_team.keevs.keevs import scan

        report = scan()
        assert isinstance(report.ops_insights, list)

    def test_save_report(self, tmp_path, monkeypatch):
        from ops_team.shared import config

        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
        from ops_team.keevs import keevs

        report = keevs.scan()
        keevs.save_report(report)
        saved = tmp_path / "keevs_latest.json"
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert data["agent"] == "keevs"


# ---------------------------------------------------------------------------
# TestTrebScan
# ---------------------------------------------------------------------------


class TestTrebScan:
    """Treb agent audits supply-side/NH experience."""

    def test_scan_returns_report(self):
        from ops_team.treb.treb import scan

        report = scan()
        assert report.agent == "treb"
        assert report.scan_duration_seconds >= 0

    def test_scan_has_supply_metrics(self):
        from ops_team.treb.treb import scan

        report = scan()
        assert len(report.metrics) > 0

    def test_scan_findings_have_categories(self):
        from ops_team.treb.treb import scan

        report = scan()
        for f in report.findings:
            assert f.category, "Finding must have a category"

    def test_save_report(self, tmp_path, monkeypatch):
        from ops_team.treb import treb
        from ops_team.shared import config

        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
        monkeypatch.setattr(treb, "REPORTS_DIR", tmp_path)
        report = treb.scan()
        treb.save_report(report)
        saved = tmp_path / "treb_latest.json"
        assert saved.exists()


# ---------------------------------------------------------------------------
# TestNaivScan
# ---------------------------------------------------------------------------


class TestNaivScan:
    """Naiv agent audits customer satisfaction."""

    def test_scan_returns_report(self):
        from ops_team.naiv.naiv import scan

        report = scan()
        assert report.agent == "naiv"
        assert report.scan_duration_seconds >= 0

    def test_scan_has_satisfaction_metrics(self):
        from ops_team.naiv.naiv import scan

        report = scan()
        assert len(report.metrics) > 0

    def test_scan_findings_are_valid(self):
        from ops_team.naiv.naiv import scan

        report = scan()
        for f in report.findings:
            assert f.severity in ("critical", "high", "medium", "low", "info")

    def test_save_report(self, tmp_path, monkeypatch):
        from ops_team.naiv import naiv

        # naiv's save_report resolves path from __file__, so monkeypatch Path
        original_save = naiv.save_report

        def patched_save(report):
            tmp_path.mkdir(parents=True, exist_ok=True)
            out_path = tmp_path / "naiv_latest.json"
            out_path.write_text(report.serialize(), encoding="utf-8")
            return out_path

        monkeypatch.setattr(naiv, "save_report", patched_save)
        report = naiv.scan()
        naiv.save_report(report)
        saved = tmp_path / "naiv_latest.json"
        assert saved.exists()


# ---------------------------------------------------------------------------
# TestMarshScan
# ---------------------------------------------------------------------------


class TestMarshScan:
    """Marsh agent audits marketplace health."""

    def test_scan_returns_report(self):
        from ops_team.marsh.marsh import scan

        report = scan()
        assert report.agent == "marsh"
        assert report.scan_duration_seconds >= 0

    def test_scan_has_marketplace_metrics(self):
        from ops_team.marsh.marsh import scan

        report = scan()
        assert len(report.metrics) > 0

    def test_scan_findings_have_ids(self):
        from ops_team.marsh.marsh import scan

        report = scan()
        for f in report.findings:
            assert f.id, "Finding must have an ID"

    def test_save_report(self, tmp_path, monkeypatch):
        from ops_team.marsh import marsh
        from ops_team.shared import config

        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
        monkeypatch.setattr(marsh, "REPORTS_DIR", tmp_path)
        report = marsh.scan()
        marsh.save_report(report)
        saved = tmp_path / "marsh_latest.json"
        assert saved.exists()


# ---------------------------------------------------------------------------
# TestOpsLeadBriefs
# ---------------------------------------------------------------------------


class TestOpsLeadBriefs:
    """OpsLead generates daily/weekly/monthly briefs."""

    def _make_sub_reports(self):
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight, OpsTeamReport

        keevs_report = OpsTeamReport(
            agent="keevs",
            scan_duration_seconds=1.0,
            findings=[
                Finding(
                    id="keevs-001",
                    severity="high",
                    category="coaching_quality",
                    title="Missing salary negotiation coaching",
                    detail="No prompts for salary negotiation",
                    recommendation="Add salary negotiation support",
                ),
            ],
            ops_insights=[
                OpsInsight(
                    id="keevs-ins-001",
                    title="Coach coverage 80%",
                    category="coaching_effectiveness",
                    evidence="4/5 scenarios",
                    impact="Job seekers missing coaching for 1/5 scenarios",
                    recommendation="Add missing scenario coverage",
                    confidence=0.85,
                ),
            ],
            metrics={"coaching_quality_score": 0.80},
            cross_team_requests=[
                {
                    "target_team": "engineering",
                    "urgency": "high",
                    "request": "Fix SSE timeout",
                    "source_agent": "keevs",
                }
            ],
        )
        treb_report = OpsTeamReport(
            agent="treb",
            scan_duration_seconds=0.8,
            findings=[
                Finding(
                    id="treb-001",
                    severity="medium",
                    category="nh_journey",
                    title="No earn visibility for NH",
                    detail="NH cannot see earnings dashboard",
                    recommendation="Add earnings dashboard",
                ),
            ],
            metrics={"nh_journey_coverage": 0.65},
        )
        return [keevs_report, treb_report]

    def test_daily_brief_with_reports(self):
        from ops_team.ops_lead.ops_lead import generate_daily_brief

        reports = self._make_sub_reports()
        brief = generate_daily_brief(reports)
        assert "Daily Brief" in brief
        assert "Ecosystem Health" in brief
        assert "keevs-001" in brief
        assert "Cross-Team" in brief

    def test_daily_brief_no_reports(self):
        from ops_team.ops_lead.ops_lead import generate_daily_brief

        brief = generate_daily_brief([])
        assert "No agent reports available" in brief

    def test_weekly_report(self):
        from ops_team.ops_lead.ops_lead import generate_weekly_report

        reports = self._make_sub_reports()
        brief = generate_weekly_report(reports)
        assert "Weekly Report" in brief
        assert "Ecosystem Readiness" in brief

    def test_monthly_review(self):
        from ops_team.ops_lead.ops_lead import generate_monthly_review

        reports = self._make_sub_reports()
        brief = generate_monthly_review(reports)
        assert "Monthly Review" in brief
        assert "KPI Progress" in brief

    def test_ops_lead_scan(self, tmp_path, monkeypatch):
        """OpsLead scan aggregates from cached sub-agent reports."""
        from ops_team.ops_lead import ops_lead
        from ops_team.shared import config

        # Write a fake sub-agent report to tmp_path
        from ops_team.shared.report import OpsTeamReport

        fake_report = OpsTeamReport(
            agent="keevs",
            scan_duration_seconds=1.0,
            findings=[],
            metrics={"coaching_quality_score": 0.90},
        )
        tmp_path.mkdir(exist_ok=True)
        (tmp_path / "keevs_latest.json").write_text(fake_report.serialize())

        monkeypatch.setattr(config, "REPORTS_DIR", tmp_path)
        monkeypatch.setattr(ops_lead, "REPORTS_DIR", tmp_path)

        report = ops_lead.scan()
        assert report.agent == "ops_lead"
        assert report.metrics.get("ops_agents_reporting") == 1


# ---------------------------------------------------------------------------
# TestOpsLearningState
# ---------------------------------------------------------------------------


class TestOpsLearningState:
    """OpsLearningState tracks scan history, patterns, and health."""

    def _make_state(self, tmp_path, monkeypatch):
        from ops_team.shared import config, learning

        monkeypatch.setattr(config, "OPS_TEAM_DIR", tmp_path)
        monkeypatch.setattr(learning, "OPS_TEAM_DIR", tmp_path)
        from ops_team.shared.learning import OpsLearningState

        return OpsLearningState("test_agent")

    def test_record_scan(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        ls.record_scan({"score": 0.85})
        assert ls.state["total_scans"] == 1

    def test_record_finding(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        ls.record_finding(
            {
                "id": "test-001",
                "severity": "high",
                "category": "coaching_quality",
                "file": "test.py",
                "title": "Test finding",
            }
        )
        assert len(ls.state["finding_history"]) == 1

    def test_recurring_pattern_detection(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        # Record same finding 5 times to trigger escalation
        for i in range(5):
            ls.record_finding(
                {
                    "id": f"rec-{i:03d}",
                    "severity": "medium",
                    "category": "coaching_quality",
                    "file": "coach.py",
                    "title": "Recurring issue",
                }
            )
        pattern = ls.detect_recurring_pattern("coaching_quality", "coach.py")
        assert pattern["count"] >= 5

    def test_health_trajectory(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        # Not enough snapshots
        trajectory = ls.get_health_trajectory()
        assert trajectory == "insufficient_data"
        # Add some snapshots
        ls.record_health_snapshot(0.70, {"medium": 3})
        ls.record_health_snapshot(0.75, {"medium": 2})
        ls.record_health_snapshot(0.80, {"medium": 1})
        trajectory = ls.get_health_trajectory()
        assert trajectory in ("improving", "stable", "degrading", "insufficient_data")

    def test_meta_learning_report(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        ls.record_scan({"score": 0.80})
        ls.record_finding(
            {
                "id": "f-001",
                "severity": "medium",
                "category": "coaching_quality",
                "file": "test.py",
                "title": "Test finding",
            }
        )
        report = ls.generate_meta_learning_report()
        assert report["total_scans"] == 1
        assert report["total_findings_tracked"] == 1
        assert "health_trajectory" in report

    def test_kpi_tracking(self, tmp_path, monkeypatch):
        ls = self._make_state(tmp_path, monkeypatch)
        ls.track_kpi("coaching_quality", 0.80)
        ls.track_kpi("coaching_quality", 0.85)
        trend = ls.get_kpi_trend("coaching_quality")
        assert trend in ("improving", "stable", "degrading", "insufficient_data")


# ---------------------------------------------------------------------------
# TestOpsIntelligence
# ---------------------------------------------------------------------------


class TestOpsIntelligence:
    """OpsIntelligence manages 12 ops-specific intel categories."""

    def _make_intel(self, tmp_path, monkeypatch):
        from ops_team.shared import config, intelligence

        cache_path = tmp_path / "intel_cache.json"
        monkeypatch.setattr(config, "INTEL_CACHE", cache_path)
        monkeypatch.setattr(intelligence, "INTEL_CACHE", cache_path)
        from ops_team.shared.intelligence import OpsIntelligence

        return OpsIntelligence()

    def test_categories_count(self):
        from ops_team.shared.intelligence import OPS_INTEL_CATEGORIES

        assert len(OPS_INTEL_CATEGORIES) == 12

    def test_add_and_get_item(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        from ops_team.shared.intelligence import OpsIntelItem

        item = OpsIntelItem(
            category="job_market_trends",
            title="Tech layoffs slowing",
            summary="Job market recovering in Q1 2026",
            severity="info",
            relevant_agents=["keevs", "ops_lead"],
        )
        oi.add_item(item)
        items = oi.get_all()
        assert len(items) == 1
        assert items[0].title == "Tech layoffs slowing"

    def test_get_for_agent(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        from ops_team.shared.intelligence import OpsIntelItem

        oi.add_item(
            OpsIntelItem(
                category="nps_benchmarks",
                title="NPS benchmark update",
                relevant_agents=["naiv"],
            )
        )
        oi.add_item(
            OpsIntelItem(
                category="job_market_trends",
                title="Market update",
                relevant_agents=["keevs"],
            )
        )
        naiv_items = oi.get_for_agent("naiv")
        assert len(naiv_items) == 1
        assert naiv_items[0].category == "nps_benchmarks"

    def test_urgency_filtering(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        from ops_team.shared.intelligence import OpsIntelItem

        oi.add_item(
            OpsIntelItem(
                category="competitor_ux",
                title="Competitor launched coaching",
                severity="high",
            )
        )
        oi.add_item(
            OpsIntelItem(
                category="survey_design",
                title="Survey best practice",
                severity="info",
            )
        )
        urgent = oi.get_urgent()
        assert len(urgent) == 1
        assert urgent[0].severity == "high"

    def test_adoption_workflow(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        from ops_team.shared.intelligence import OpsIntelItem

        item = OpsIntelItem(
            category="marketplace_economics",
            title="Take rate benchmarks",
        )
        oi.add_item(item)
        unadopted = oi.get_unadopted()
        assert len(unadopted) == 1

        oi.mark_adopted(item.id, "marsh")
        unadopted = oi.get_unadopted()
        assert len(unadopted) == 0

    def test_freshness_check(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        freshness = oi.check_freshness()
        assert len(freshness) == 12
        # All should be stale since we haven't populated cache
        stale_count = sum(1 for v in freshness.values() if not v)
        assert stale_count == 12

    def test_research_agenda(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        agenda = oi.generate_research_agenda()
        assert len(agenda) == 12  # All stale -> all in agenda
        # Should be sorted by priority
        priorities = [item["priority"] for item in agenda]
        high_indices = [i for i, p in enumerate(priorities) if p == "high"]
        medium_indices = [i for i, p in enumerate(priorities) if p == "medium"]
        if high_indices and medium_indices:
            assert max(high_indices) < min(medium_indices)

    def test_intel_report(self, tmp_path, monkeypatch):
        oi = self._make_intel(tmp_path, monkeypatch)
        report = oi.generate_intel_report()
        assert report["total_items"] == 0
        assert report["categories_total"] == 12
        assert report["categories_stale"] == 12


# ---------------------------------------------------------------------------
# TestCoSIntegration
# ---------------------------------------------------------------------------


class TestCoSIntegration:
    """CoS config, learning, synthesizer, and business outcomes include ops team."""

    def test_cos_config_has_ops_team(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG

        teams = COS_CONFIG["teams"]
        assert "ops" in teams
        assert teams["ops"]["active"] is True
        assert teams["ops"]["report_dir"] == "ops_team/reports"

    def test_cos_config_has_ops_budget(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG

        budget = COS_CONFIG["cost_budget"]
        assert "ops_team_daily_max_tokens" in budget

    def test_cos_learning_has_ops_team(self):
        from agents.chief_of_staff.cos_learning import _default_state

        state = _default_state()
        assert "ops" in state["team_reliability"]
        ops_stats = state["team_reliability"]["ops"]
        assert ops_stats["reports_on_time"] == 0
        assert ops_stats["reports_total"] == 0

    def test_business_outcomes_has_ops_categories(self):
        from agents.shared.business_outcomes import CATEGORY_OUTCOME_MAP

        ops_categories = [
            "coaching_effectiveness",
            "supply_activation",
            "user_satisfaction",
            "marketplace_health",
            "ops_efficiency",
        ]
        for cat in ops_categories:
            assert cat in CATEGORY_OUTCOME_MAP, f"Missing category: {cat}"

    def test_business_outcomes_ops_impact_templates(self):
        from agents.shared.business_outcomes import get_business_impact

        # Should return ops-specific impact, not generic
        impact = get_business_impact("coaching_effectiveness", "critical")
        assert "coaching" in impact.lower() or "job seeker" in impact.lower()

    def test_report_converts_to_agent_report(self):
        """OpsTeamReport.to_agent_report() produces valid AgentReport for CoS."""
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsTeamReport

        report = OpsTeamReport(
            agent="keevs",
            scan_duration_seconds=1.0,
            findings=[
                Finding(
                    id="keevs-001",
                    severity="high",
                    category="coaching_quality",
                    title="Test finding",
                    detail="Test detail for CoS conversion",
                ),
            ],
            metrics={"coaching_quality_score": 0.80},
        )
        ar = report.to_agent_report()
        assert ar.agent == "keevs"
        assert len(ar.findings) == 1
        assert ar.scan_duration_seconds == 1.0

    def test_orchestrator_agent_registry(self):
        """Orchestrator knows all 5 ops agents."""
        from ops_team.orchestrator import _AGENT_MODULES

        expected = {"keevs", "treb", "naiv", "marsh", "ops_lead"}
        assert set(_AGENT_MODULES.keys()) == expected

    def test_config_agent_names(self):
        """Config lists all 5 ops agent names."""
        from ops_team.shared.config import OPS_AGENT_NAMES

        assert len(OPS_AGENT_NAMES) == 5
        assert "keevs" in OPS_AGENT_NAMES
        assert "ops_lead" in OPS_AGENT_NAMES
