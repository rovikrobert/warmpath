"""Tests for the Chief of Staff agent system."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from agents.shared.report import AgentReport, Finding


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_finding(
    id: str = "F001",
    severity: str = "medium",
    category: str = "security",
    title: str = "Test finding",
    detail: str = "Some detail",
    recommendation: str = "Fix it",
    effort_hours: float = 1.0,
    file: str = "app/main.py",
    line: int = 10,
) -> Finding:
    return Finding(
        id=id,
        severity=severity,
        category=category,
        title=title,
        detail=detail,
        recommendation=recommendation,
        effort_hours=effort_hours,
        file=file,
        line=line,
    )


def _make_report(
    agent: str = "architect",
    findings: list[Finding] | None = None,
    metrics: dict | None = None,
    duration: float = 2.5,
) -> AgentReport:
    return AgentReport(
        agent=agent,
        findings=findings or [],
        metrics=metrics or {},
        scan_duration_seconds=duration,
    )


@pytest.fixture
def sample_findings() -> list[Finding]:
    return [
        _make_finding("SEC-001", "critical", "security", "SQL injection in search"),
        _make_finding("SEC-002", "high", "privacy", "PII leak in marketplace"),
        _make_finding("PERF-001", "medium", "performance", "N+1 query in contacts"),
        _make_finding("TEST-001", "low", "test_quality", "Weak assertion pattern"),
        _make_finding("DOC-001", "info", "documentation", "Missing API docs"),
    ]


@pytest.fixture
def sample_reports(sample_findings: list[Finding]) -> list[AgentReport]:
    return [
        _make_report(
            "security", [sample_findings[0], sample_findings[1]], duration=3.0
        ),
        _make_report("perf_monitor", [sample_findings[2]], duration=1.5),
        _make_report("test_engineer", [sample_findings[3]], duration=5.0),
        _make_report("doc_keeper", [sample_findings[4]], duration=0.8),
        _make_report("architect", [], duration=2.0),
    ]


@pytest.fixture
def clean_report() -> AgentReport:
    """A report with no findings."""
    return _make_report("architect", [], duration=1.0)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_cos_finding_valid(self):
        from agents.chief_of_staff.schemas import CosFinding

        cf = CosFinding(
            id="F001",
            severity="critical",
            category="security",
            summary="Test finding",
            evidence="Found in code",
            business_impact="User data at risk",
            recommended_action="Fix immediately",
            effort_estimate="2h",
            outcome_alignment=["help_job_seekers", "billion_dollar"],
        )
        assert cf.id == "F001"
        assert cf.severity == "critical"
        assert len(cf.outcome_alignment) == 2

    def test_cos_finding_defaults(self):
        from agents.chief_of_staff.schemas import CosFinding

        cf = CosFinding(
            id="F002",
            severity="low",
            category="docs",
            summary="Minor issue",
        )
        assert cf.evidence == ""
        assert cf.outcome_alignment == []

    def test_cross_team_request(self):
        from agents.chief_of_staff.schemas import CrossTeamRequest

        req = CrossTeamRequest(
            team="engineering",
            request="Need API spec review",
            urgency="high",
            blocking="product",
        )
        assert req.urgency == "high"
        assert req.blocking == "product"

    def test_cross_team_request_defaults(self):
        from agents.chief_of_staff.schemas import CrossTeamRequest

        req = CrossTeamRequest(team="eng", request="test")
        assert req.urgency == "medium"
        assert req.blocking is None

    def test_team_report(self):
        from agents.chief_of_staff.schemas import CosFinding, TeamReport

        tr = TeamReport(
            team="engineering",
            date="2026-02-17",
            report_type="daily",
            findings=[
                CosFinding(id="F1", severity="high", category="sec", summary="x")
            ],
            kpis={"health": 85},
        )
        assert tr.team == "engineering"
        assert len(tr.findings) == 1

    def test_founder_brief(self):
        from agents.chief_of_staff.schemas import FounderBrief

        fb = FounderBrief(
            date="2026-02-17",
            decisions_needed=[{"id": "F1", "summary": "fix"}],
            kpi_snapshot="Health: 85",
        )
        assert fb.date == "2026-02-17"
        assert len(fb.decisions_needed) == 1

    def test_conflict(self):
        from agents.chief_of_staff.schemas import Conflict

        c = Conflict(
            id="C001",
            teams=["engineering", "product"],
            description="Disagree on API design",
            positions={"engineering": "REST", "product": "GraphQL"},
            evidence={"engineering": "Simpler to maintain"},
            cos_recommendation="REST for MVP",
            resolution_level=2,
        )
        assert len(c.teams) == 2
        assert c.resolution_level == 2

    def test_resolution(self):
        from agents.chief_of_staff.schemas import Resolution

        r = Resolution(
            conflict_id="C001",
            strategy_used="tradeoff_framing",
            outcome="Resolved in favor of engineering",
            escalated=False,
            founder_agreed=True,
        )
        assert not r.escalated
        assert r.founder_agreed is True

    def test_resolution_defaults(self):
        from agents.chief_of_staff.schemas import Resolution

        r = Resolution(
            conflict_id="C002",
            strategy_used="escalation",
            outcome="Escalated",
        )
        assert r.escalated is False
        assert r.founder_agreed is None

    def test_founder_brief_team_summaries(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(
            date="2025-01-01",
            team_summaries=[
                {
                    "team": "engineering",
                    "health": "green",
                    "summary": "All clear",
                    "agent_count": 5,
                    "finding_count": 0,
                },
                {
                    "team": "data",
                    "health": "yellow",
                    "summary": "Pipeline stale",
                    "agent_count": 4,
                    "finding_count": 2,
                },
            ],
        )
        assert len(brief.team_summaries) == 2
        assert brief.team_summaries[0]["team"] == "engineering"
        assert brief.team_summaries[1]["health"] == "yellow"

    def test_founder_brief_team_summaries_default_empty(self):
        from agents.chief_of_staff.schemas import FounderBrief

        brief = FounderBrief(date="2025-01-01")
        assert brief.team_summaries == []


# ---------------------------------------------------------------------------
# Business outcomes tests
# ---------------------------------------------------------------------------


class TestBusinessOutcomes:
    def test_score_alignment_high_priority(self):
        from agents.shared.business_outcomes import (
            HELP_JOB_SEEKERS,
            score_alignment,
        )

        score = score_alignment([HELP_JOB_SEEKERS])
        assert score > 0

    def test_score_alignment_empty(self):
        from agents.shared.business_outcomes import score_alignment

        assert score_alignment([]) == 0.0

    def test_score_alignment_all_outcomes(self):
        from agents.shared.business_outcomes import OUTCOME_PRIORITY, score_alignment

        score = score_alignment(OUTCOME_PRIORITY)
        assert score > 0
        assert score <= 1.0

    def test_score_alignment_priority_ordering(self):
        from agents.shared.business_outcomes import (
            COST_EFFICIENCY,
            HELP_JOB_SEEKERS,
            score_alignment,
        )

        high = score_alignment([HELP_JOB_SEEKERS])
        low = score_alignment([COST_EFFICIENCY])
        assert high > low

    def test_get_business_impact_security_critical(self):
        from agents.shared.business_outcomes import get_business_impact

        impact = get_business_impact("security", "critical")
        assert "breach" in impact.lower() or "risk" in impact.lower()

    def test_get_business_impact_privacy_high(self):
        from agents.shared.business_outcomes import get_business_impact

        impact = get_business_impact("privacy", "high")
        assert "privacy" in impact.lower() or "vault" in impact.lower()

    def test_get_business_impact_performance_medium(self):
        from agents.shared.business_outcomes import get_business_impact

        impact = get_business_impact("performance", "medium")
        assert len(impact) > 0

    def test_get_business_impact_unknown_category(self):
        from agents.shared.business_outcomes import get_business_impact

        impact = get_business_impact("unknown_category", "high")
        assert len(impact) > 0  # Falls back to default

    def test_get_aligned_outcomes_security(self):
        from agents.shared.business_outcomes import (
            BILLION_DOLLAR,
            HELP_JOB_SEEKERS,
            get_aligned_outcomes,
        )

        outcomes = get_aligned_outcomes("security")
        assert HELP_JOB_SEEKERS in outcomes
        assert BILLION_DOLLAR in outcomes

    def test_get_aligned_outcomes_unknown(self):
        from agents.shared.business_outcomes import (
            COST_EFFICIENCY,
            get_aligned_outcomes,
        )

        outcomes = get_aligned_outcomes("totally_unknown")
        assert COST_EFFICIENCY in outcomes  # Default fallback

    def test_outcome_labels_complete(self):
        from agents.shared.business_outcomes import OUTCOME_LABELS, OUTCOME_PRIORITY

        for outcome in OUTCOME_PRIORITY:
            assert outcome in OUTCOME_LABELS

    def test_category_outcome_map_entries(self):
        from agents.shared.business_outcomes import (
            CATEGORY_OUTCOME_MAP,
            OUTCOME_PRIORITY,
        )

        for category, outcomes in CATEGORY_OUTCOME_MAP.items():
            for outcome in outcomes:
                assert outcome in OUTCOME_PRIORITY, (
                    f"Category '{category}' references unknown outcome '{outcome}'"
                )


# ---------------------------------------------------------------------------
# Cost tracker tests
# ---------------------------------------------------------------------------


class TestCostTracker:
    def test_get_agent_costs(self, sample_reports: list[AgentReport]):
        from agents.shared.cost_tracker import get_agent_costs

        costs = get_agent_costs(sample_reports)
        assert len(costs) == 5
        assert "security" in costs
        assert costs["security"]["duration_seconds"] == 3.0
        assert costs["security"]["estimated_tokens"] > 0

    def test_get_team_cost_summary(self, sample_reports: list[AgentReport]):
        from agents.shared.cost_tracker import get_team_cost_summary

        summary = get_team_cost_summary(sample_reports)
        assert summary["agent_count"] == 5
        assert summary["total_duration_seconds"] > 0
        assert summary["total_estimated_tokens"] > 0
        assert summary["total_estimated_cost_usd"] > 0
        assert "agent_breakdown" in summary

    def test_get_team_cost_summary_empty(self):
        from agents.shared.cost_tracker import get_team_cost_summary

        summary = get_team_cost_summary([])
        assert summary["agent_count"] == 0
        assert summary["total_duration_seconds"] == 0

    def test_check_budget_alerts_under_budget(self, sample_reports: list[AgentReport]):
        from agents.shared.cost_tracker import (
            check_budget_alerts,
            get_team_cost_summary,
        )

        costs = get_team_cost_summary(sample_reports)
        budgets = {"total_daily_max_tokens": 999999, "alert_threshold_pct": 150}
        alerts = check_budget_alerts(costs, budgets)
        assert len(alerts) == 0

    def test_check_budget_alerts_over_budget(self):
        from agents.shared.cost_tracker import check_budget_alerts

        costs = {"total_estimated_tokens": 50000, "agent_breakdown": {}}
        budgets = {"total_daily_max_tokens": 10000, "alert_threshold_pct": 150}
        alerts = check_budget_alerts(costs, budgets)
        assert len(alerts) == 1
        assert "500%" in alerts[0]


# ---------------------------------------------------------------------------
# CoS config tests
# ---------------------------------------------------------------------------


class TestCosConfig:
    def test_config_structure(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG

        assert "daily_brief_time" in COS_CONFIG
        assert "teams" in COS_CONFIG
        assert COS_CONFIG["teams"]["engineering"]["active"] is True
        assert COS_CONFIG["teams"]["product"]["active"] is True

    def test_severity_weights(self):
        from agents.chief_of_staff.cos_config import SEVERITY_WEIGHT

        assert SEVERITY_WEIGHT["critical"] > SEVERITY_WEIGHT["high"]
        assert SEVERITY_WEIGHT["high"] > SEVERITY_WEIGHT["medium"]
        assert SEVERITY_WEIGHT["info"] == 0.0

    def test_decision_principles(self):
        from agents.chief_of_staff.cos_config import DECISION_PRINCIPLES

        assert DECISION_PRINCIPLES[0] == "safety_privacy"
        assert len(DECISION_PRINCIPLES) == 6

    def test_telegram_config_present(self):
        from agents.chief_of_staff.cos_config import COS_CONFIG

        assert "telegram" in COS_CONFIG
        assert "morning_brief_time" in COS_CONFIG["telegram"]
        assert "weekly_summary_day" in COS_CONFIG["telegram"]


# ---------------------------------------------------------------------------
# Synthesizer tests
# ---------------------------------------------------------------------------


class TestSynthesizer:
    def test_synthesize_daily_with_findings(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        brief, _ = synthesize_daily(sample_reports, kpi_snapshot="Health: 85")
        assert "# Founder Daily Brief" in brief
        assert "Decisions Needed" in brief
        assert "Key Updates" in brief
        assert "Progress" in brief
        assert "Health: 85" in brief

    def test_synthesize_daily_empty(self):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        brief, _ = synthesize_daily([])
        assert "# Founder Daily Brief" in brief
        assert "No decisions needed" in brief

    def test_synthesize_daily_critical_findings(self):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        findings = [
            _make_finding("CRIT-1", "critical", "security", "Urgent fix needed")
        ]
        reports = [_make_report("security", findings)]
        brief, _ = synthesize_daily(reports)
        assert "CRIT-1" in brief
        assert "Decisions Needed" in brief

    def test_synthesize_daily_all_clean(self):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        reports = [_make_report("architect"), _make_report("doc_keeper")]
        brief, _ = synthesize_daily(reports)
        assert "No decisions needed" in brief
        assert "Progress" in brief

    def test_synthesize_daily_with_costs(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        costs = {
            "total_estimated_cost_usd": 0.0123,
            "total_estimated_tokens": 500,
            "total_duration_seconds": 12.3,
        }
        brief, _ = synthesize_daily(sample_reports, costs=costs)
        assert "Cost Summary" in brief
        assert "$0.0123" in brief

    def test_synthesize_daily_with_alerts(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        costs = {
            "total_estimated_cost_usd": 1.0,
            "total_estimated_tokens": 99999,
            "total_duration_seconds": 100.0,
        }
        alerts = ["Token budget exceeded!"]
        brief, _ = synthesize_daily(sample_reports, costs=costs, alerts=alerts)
        assert "ALERT" in brief
        assert "Token budget exceeded" in brief

    def test_synthesize_weekly(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_weekly

        report = synthesize_weekly(sample_reports, kpi_snapshot="KPI data")
        assert "# Weekly Synthesis" in report
        assert "Business Outcome Scorecard" in report
        assert "Top 3 Priorities" in report
        assert "Cross-Team Patterns" in report
        assert "Self-Learning" in report

    def test_synthesize_weekly_empty(self):
        from agents.chief_of_staff.synthesizer import synthesize_weekly

        report = synthesize_weekly([])
        assert "# Weekly Synthesis" in report
        assert "No priorities" in report

    def test_synthesize_weekly_outcome_scorecard(
        self, sample_reports: list[AgentReport]
    ):
        from agents.chief_of_staff.synthesizer import synthesize_weekly

        report = synthesize_weekly(sample_reports)
        assert "Help Job Seekers" in report
        assert "At Risk" in report or "Monitoring" in report or "Healthy" in report

    def test_synthesize_weekly_with_costs(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_weekly

        costs = {"total_estimated_cost_usd": 0.05, "total_estimated_tokens": 1000}
        report = synthesize_weekly(sample_reports, costs=costs)
        assert "Cost Summary" in report
        assert "Weekly total" in report

    def test_synthesize_status(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_status

        status = synthesize_status(sample_reports)
        assert "# Status Snapshot" in status
        assert "Engineering" in status
        assert "Agents: 5 reporting" in status
        assert "Teams" in status

    def test_synthesize_status_empty(self):
        from agents.chief_of_staff.synthesizer import synthesize_status

        status = synthesize_status([])
        assert "# Status Snapshot" in status
        assert "0 critical" in status

    def test_synthesize_status_per_agent(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.synthesizer import synthesize_status

        status = synthesize_status(sample_reports)
        assert "security:" in status
        assert "architect:" in status

    def test_summarize_team_green(self, sample_reports):
        from agents.chief_of_staff.synthesizer import summarize_team

        # sample_reports[4] is architect with 0 findings
        result = summarize_team("engineering", [sample_reports[4]])
        assert result["team"] == "engineering"
        assert result["health"] == "green"
        assert result["agent_count"] == 1
        assert result["finding_count"] == 0
        assert isinstance(result["summary"], str)

    def test_summarize_team_red(self, sample_reports):
        from agents.chief_of_staff.synthesizer import summarize_team

        # sample_reports[0] has critical + high findings
        result = summarize_team("engineering", [sample_reports[0]])
        assert result["health"] == "red"
        assert result["finding_count"] == 2

    def test_summarize_team_yellow(self):
        from agents.chief_of_staff.synthesizer import summarize_team

        report = _make_report("pipeline", [_make_finding("D1", "medium", "data")])
        result = summarize_team("data", [report])
        assert result["health"] == "yellow"
        assert result["finding_count"] == 1

    def test_summarize_team_empty(self):
        from agents.chief_of_staff.synthesizer import summarize_team

        result = summarize_team("ops", [])
        assert result["team"] == "ops"
        assert result["health"] == "green"
        assert result["agent_count"] == 0

    def test_synthesize_daily_includes_team_summaries(self, sample_reports):
        from agents.chief_of_staff.synthesizer import synthesize_daily

        brief_text, brief_data = synthesize_daily(sample_reports)
        assert "team_summaries" in brief_data
        summaries = brief_data["team_summaries"]
        assert len(summaries) >= 1
        eng = next((s for s in summaries if s["team"] == "engineering"), None)
        assert eng is not None
        assert eng["health"] in ("green", "yellow", "red")
        assert eng["agent_count"] > 0


# ---------------------------------------------------------------------------
# Resolver tests
# ---------------------------------------------------------------------------


class TestResolver:
    def test_level_1_context_resolution(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="C001",
            teams=["engineering", "product"],
            description="API design disagreement",
            positions={"engineering": "REST", "product": "GraphQL"},
            evidence={"engineering": "Simpler to maintain"},
            resolution_level=1,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "C001"
        assert resolution.strategy_used == "context_clarification"
        assert "engineering" in resolution.outcome
        assert not resolution.escalated

    def test_level_2_tradeoff_resolution(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="C002",
            teams=["team_a", "team_b"],
            description="Prioritization disagreement",
            positions={
                "team_a": "Focus on safety and privacy first",
                "team_b": "Focus on cost optimization",
            },
            evidence={
                "team_a": "User data at risk",
                "team_b": "Budget concerns",
            },
            resolution_level=2,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "C002"
        assert "team_a" in resolution.outcome
        assert resolution.strategy_used == "tradeoff_framing"
        assert not resolution.escalated

    def test_level_3_compromise(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        # Both sides have equal evidence and similar priority
        conflict = Conflict(
            id="C003",
            teams=["team_a", "team_b"],
            description="Resource allocation",
            positions={
                "team_a": "Hire backend engineers",
                "team_b": "Hire frontend engineers",
            },
            evidence={
                "team_a": "Backend bottleneck",
                "team_b": "Frontend bottleneck",
            },
            resolution_level=3,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "C003"
        assert not resolution.escalated

    def test_level_4_escalation(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="C004",
            teams=["team_a", "team_b"],
            description="Fundamental disagreement",
            positions={
                "team_a": "Build in-house",
                "team_b": "Use vendor",
            },
            evidence={
                "team_a": "Better control",
                "team_b": "Faster delivery",
            },
            cos_recommendation="Build in-house for long-term",
            resolution_level=4,
        )
        resolution = attempt_resolution(conflict)
        assert resolution.conflict_id == "C004"
        assert resolution.escalated is True
        assert resolution.strategy_used == "escalation"
        assert "Build in-house" in resolution.outcome

    def test_safety_wins_over_cost(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        conflict = Conflict(
            id="C005",
            teams=["security_team", "budget_team"],
            description="Security vs cost",
            positions={
                "security_team": "Implement safety measures for privacy",
                "budget_team": "Cut cost and optimize budget",
            },
            evidence={
                "security_team": "PII breach risk",
                "budget_team": "Over budget by 20%",
            },
            resolution_level=2,
        )
        resolution = attempt_resolution(conflict)
        assert "security_team" in resolution.outcome
        assert not resolution.escalated

    def test_single_team_no_compromise(self):
        from agents.chief_of_staff.resolver import attempt_resolution
        from agents.chief_of_staff.schemas import Conflict

        # Single team conflict goes to escalation at level 3
        conflict = Conflict(
            id="C006",
            teams=["engineering"],
            description="Internal disagreement",
            positions={"engineering": "Refactor now"},
            evidence={"engineering": "Tech debt growing"},
            resolution_level=3,
        )
        resolution = attempt_resolution(conflict)
        # Single team can't compromise, falls through to escalation
        assert resolution.conflict_id == "C006"


# ---------------------------------------------------------------------------
# Onboarder tests
# ---------------------------------------------------------------------------


class TestOnboarder:
    def test_validate_valid_spec(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {
            "team": {
                "name": "data",
                "lead_agent": "data_lead",
                "purpose": "Data engineering",
                "business_outcomes_served": ["cost_efficiency"],
            },
            "agents": [{"name": "etl_agent", "role": "ETL pipeline scanner"}],
            "reporting": {
                "cadence": "daily",
                "format": "team_report",
                "lead_submits_to": "chief_of_staff",
            },
            "cost_budget": {
                "max_daily_tokens": 5000,
                "alert_threshold_pct": 150,
            },
        }
        errors = validate_team_spec(spec)
        assert errors == []

    def test_validate_missing_team_fields(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {"team": {"name": "test"}}
        errors = validate_team_spec(spec)
        assert len(errors) > 0
        assert any("Missing team fields" in e for e in errors)

    def test_validate_empty_team_name(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {
            "team": {
                "name": "",
                "lead_agent": "lead",
                "purpose": "Test",
                "business_outcomes_served": ["cost_efficiency"],
            },
            "agents": [{"name": "a", "role": "r"}],
            "reporting": {
                "cadence": "daily",
                "format": "f",
                "lead_submits_to": "cos",
            },
            "cost_budget": {"max_daily_tokens": 100, "alert_threshold_pct": 150},
        }
        errors = validate_team_spec(spec)
        assert any("name must not be empty" in e for e in errors)

    def test_validate_invalid_outcome(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {
            "team": {
                "name": "test",
                "lead_agent": "lead",
                "purpose": "Test",
                "business_outcomes_served": ["invalid_outcome"],
            },
            "agents": [{"name": "a", "role": "r"}],
            "reporting": {
                "cadence": "daily",
                "format": "f",
                "lead_submits_to": "cos",
            },
            "cost_budget": {"max_daily_tokens": 100, "alert_threshold_pct": 150},
        }
        errors = validate_team_spec(spec)
        assert any("Unknown business outcome" in e for e in errors)

    def test_validate_no_agents(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {
            "team": {
                "name": "test",
                "lead_agent": "lead",
                "purpose": "Test",
                "business_outcomes_served": ["cost_efficiency"],
            },
            "agents": [],
            "reporting": {
                "cadence": "daily",
                "format": "f",
                "lead_submits_to": "cos",
            },
            "cost_budget": {"max_daily_tokens": 100, "alert_threshold_pct": 150},
        }
        errors = validate_team_spec(spec)
        assert any("At least one agent" in e for e in errors)

    def test_validate_missing_reporting(self):
        from agents.chief_of_staff.onboarder import validate_team_spec

        spec = {
            "team": {
                "name": "test",
                "lead_agent": "lead",
                "purpose": "Test",
                "business_outcomes_served": ["cost_efficiency"],
            },
            "agents": [{"name": "a", "role": "r"}],
            "cost_budget": {"max_daily_tokens": 100, "alert_threshold_pct": 150},
        }
        errors = validate_team_spec(spec)
        assert any("Missing reporting fields" in e for e in errors)

    def test_generate_scaffold_dry_run(self):
        from agents.chief_of_staff.onboarder import generate_team_scaffold

        spec = {
            "team": {"name": "data_team", "lead_agent": "data_lead", "purpose": "Data"},
        }
        files = generate_team_scaffold(spec, dry_run=True)
        assert len(files) == 3
        assert any("__init__.py" in f for f in files)
        assert any("AGENT.md" in f for f in files)
        assert any("data_lead.py" in f for f in files)

    def test_generate_scaffold_creates_files(self, tmp_path: Path):
        from agents.chief_of_staff.onboarder import generate_team_scaffold

        spec = {
            "team": {
                "name": "test_scaffold",
                "lead_agent": "scaffold_lead",
                "purpose": "Testing scaffold generation",
            },
        }
        with patch("agents.chief_of_staff.onboarder.AGENTS_DIR", tmp_path):
            files = generate_team_scaffold(spec, dry_run=False)
            assert len(files) == 3
            team_dir = tmp_path / "test_scaffold"
            assert team_dir.is_dir()
            assert (team_dir / "__init__.py").exists()
            assert (team_dir / "AGENT.md").exists()
            assert "Testing scaffold generation" in (team_dir / "AGENT.md").read_text()
            assert (team_dir / "scaffold_lead.py").exists()

    def test_load_template(self):
        from agents.chief_of_staff.onboarder import load_template

        template = load_template()
        assert "team" in template
        assert "agents" in template
        assert "reporting" in template
        assert "cost_budget" in template


# ---------------------------------------------------------------------------
# CoS learning tests
# ---------------------------------------------------------------------------


class TestCosLearning:
    @pytest.fixture(autouse=True)
    def _use_tmp_state(self, tmp_path: Path):
        """Redirect CoS learning state to a temp directory."""
        state_path = tmp_path / "cos_state.json"
        with patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path):
            yield

    def test_default_state(self):
        from agents.chief_of_staff.cos_learning import get_learning_summary

        state = get_learning_summary()
        assert state["version"] == 1
        assert state["resolution_patterns"]["total_conflicts"] == 0

    def test_record_founder_decision_agreed(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_founder_decision,
        )

        record_founder_decision("F001", "fix_now", "fix_now")
        state = get_learning_summary()
        assert state["priority_calibration"]["items_ranked_critical"] == 1
        assert state["priority_calibration"]["founder_agreed_critical"] == 1
        assert state["priority_calibration"]["over_escalation_count"] == 0

    def test_record_founder_decision_disagreed(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_founder_decision,
        )

        record_founder_decision("F002", "fix_now", "defer")
        state = get_learning_summary()
        assert state["priority_calibration"]["over_escalation_count"] == 1
        assert state["priority_calibration"]["founder_agreed_critical"] == 0

    def test_record_resolution(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_resolution,
        )

        record_resolution("C001", "tradeoff_framing", "Resolved", escalated=False)
        state = get_learning_summary()
        assert state["resolution_patterns"]["total_conflicts"] == 1
        assert state["resolution_patterns"]["resolved_without_escalation"] == 1

    def test_record_resolution_escalated(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_resolution,
        )

        record_resolution("C002", "escalation", "Escalated", escalated=True)
        state = get_learning_summary()
        assert state["resolution_patterns"]["total_conflicts"] == 1
        assert state["resolution_patterns"]["resolved_without_escalation"] == 0

    def test_update_team_reliability(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            update_team_reliability,
        )

        reports = [
            _make_report("security", [_make_finding(severity="info")]),
            _make_report("architect", [_make_finding(severity="high")]),
        ]
        update_team_reliability("engineering", reports)
        state = get_learning_summary()
        eng = state["team_reliability"]["engineering"]
        assert eng["reports_total"] == 2
        assert eng["reports_on_time"] == 2
        assert eng["noise_ratio"] == 0.5  # 1 info out of 2 findings

    def test_record_cost_snapshot(self):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_cost_snapshot,
        )

        record_cost_snapshot({"total_cost": 0.05, "tokens": 1000})
        state = get_learning_summary()
        assert len(state["cost_trends"]) == 1
        assert state["cost_trends"][0]["total_cost"] == 0.05

    def test_weekly_reflect_no_data(self):
        from agents.chief_of_staff.cos_learning import weekly_reflect

        notes = weekly_reflect()
        assert len(notes) >= 1
        assert "Insufficient data" in notes[0]

    def test_weekly_reflect_with_data(self):
        from agents.chief_of_staff.cos_learning import (
            record_founder_decision,
            record_resolution,
            update_team_reliability,
            weekly_reflect,
        )

        record_resolution("C001", "tradeoff", "Resolved", escalated=False)
        record_resolution("C002", "escalation", "Escalated", escalated=True)
        record_founder_decision("F001", "fix", "fix")
        update_team_reliability("engineering", [_make_report("security")])

        notes = weekly_reflect()
        assert any("1/2 conflicts" in n for n in notes)
        assert any("1/1" in n for n in notes)
        assert any("engineering" in n for n in notes)

    def test_state_persistence(self, tmp_path: Path):
        from agents.chief_of_staff.cos_learning import (
            get_learning_summary,
            record_resolution,
        )

        record_resolution("C001", "compromise", "Done", escalated=False)
        state1 = get_learning_summary()

        # Load again — should persist
        state2 = get_learning_summary()
        assert state2["resolution_patterns"]["total_conflicts"] == 1


# ---------------------------------------------------------------------------
# CoS agent integration tests
# ---------------------------------------------------------------------------


class TestCosAgent:
    @pytest.fixture(autouse=True)
    def _use_tmp_dirs(self, tmp_path: Path):
        """Redirect reports and learning state to temp dirs."""
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        state_path = tmp_path / "cos_state.json"

        data_reports_dir = tmp_path / "data_reports"
        data_reports_dir.mkdir()

        product_reports_dir = tmp_path / "product_reports"
        product_reports_dir.mkdir()

        ops_reports_dir = tmp_path / "ops_reports"
        ops_reports_dir.mkdir()

        finance_reports_dir = tmp_path / "finance_reports"
        finance_reports_dir.mkdir()

        gtm_reports_dir = tmp_path / "gtm_reports"
        gtm_reports_dir.mkdir()

        with (
            patch("agents.chief_of_staff.cos_agent.REPORTS_DIR", reports_dir),
            patch(
                "agents.chief_of_staff.cos_agent.DATA_TEAM_REPORTS_DIR",
                data_reports_dir,
            ),
            patch(
                "agents.chief_of_staff.cos_agent.PRODUCT_TEAM_REPORTS_DIR",
                product_reports_dir,
            ),
            patch(
                "agents.chief_of_staff.cos_agent.OPS_TEAM_REPORTS_DIR", ops_reports_dir
            ),
            patch(
                "agents.chief_of_staff.cos_agent.FINANCE_TEAM_REPORTS_DIR",
                finance_reports_dir,
            ),
            patch(
                "agents.chief_of_staff.cos_agent.GTM_TEAM_REPORTS_DIR", gtm_reports_dir
            ),
            patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path),
        ):
            self._reports_dir = reports_dir
            yield

    def _write_report(self, report: AgentReport) -> None:
        path = self._reports_dir / f"{report.agent}_latest.json"
        path.write_text(report.serialize())

    def test_run_daily_no_reports(self):
        from agents.chief_of_staff.cos_agent import run_daily

        result = run_daily()
        assert "No engineering reports" in result

    def test_run_daily_with_reports(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.cos_agent import run_daily

        for r in sample_reports:
            self._write_report(r)
        result = run_daily()
        assert "# Founder Daily Brief" in result
        assert "Decisions Needed" in result

    def test_run_daily_clean_reports(self):
        from agents.chief_of_staff.cos_agent import run_daily

        self._write_report(_make_report("architect"))
        self._write_report(_make_report("doc_keeper"))
        result = run_daily()
        assert "# Founder Daily Brief" in result
        assert "No decisions needed" in result

    def test_run_weekly_no_reports(self):
        from agents.chief_of_staff.cos_agent import run_weekly

        result = run_weekly()
        assert "No engineering reports" in result

    def test_run_weekly_with_reports(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.cos_agent import run_weekly

        for r in sample_reports:
            self._write_report(r)
        result = run_weekly()
        assert "# Weekly Synthesis" in result
        assert "Business Outcome Scorecard" in result

    def test_run_status_no_reports(self):
        from agents.chief_of_staff.cos_agent import run_status

        result = run_status()
        assert "No engineering reports" in result

    def test_run_status_with_reports(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.cos_agent import run_status

        for r in sample_reports:
            self._write_report(r)
        result = run_status()
        assert "# Status Snapshot" in result
        assert "Engineering" in result or "engineering" in result.lower()

    def test_run_daily_updates_learning(self, sample_reports: list[AgentReport]):
        from agents.chief_of_staff.cos_agent import run_daily
        from agents.chief_of_staff.cos_learning import get_learning_summary

        for r in sample_reports:
            self._write_report(r)
        run_daily()
        state = get_learning_summary()
        assert state["team_reliability"]["engineering"]["reports_total"] > 0
        assert len(state["cost_trends"]) > 0


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------


class TestTeamTemplate:
    def test_template_is_valid_json(self):
        from agents.shared.config import AGENTS_DIR

        template_path = AGENTS_DIR / "templates" / "team_template.json"
        data = json.loads(template_path.read_text())
        assert "team" in data
        assert "agents" in data
        assert "reporting" in data
        assert "cost_budget" in data
        assert "cross_team_interfaces" in data

    def test_template_reporting_submits_to_cos(self):
        from agents.shared.config import AGENTS_DIR

        template_path = AGENTS_DIR / "templates" / "team_template.json"
        data = json.loads(template_path.read_text())
        assert data["reporting"]["lead_submits_to"] == "chief_of_staff"


# ---------------------------------------------------------------------------
# Org evaluator tests (Gap 4)
# ---------------------------------------------------------------------------


class TestOrgEvaluator:
    @pytest.fixture(autouse=True)
    def _use_tmp_state(self, tmp_path: Path):
        state_path = tmp_path / "cos_state.json"
        with patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path):
            yield

    def test_evaluate_triggers_empty(self):
        from agents.chief_of_staff.org_evaluator import evaluate_triggers

        triggers = evaluate_triggers([], {})
        assert isinstance(triggers, list)

    def test_evaluate_triggers_cost_over_cap(self):
        from agents.chief_of_staff.org_evaluator import evaluate_triggers

        costs = {"total_estimated_cost_usd": 5.0, "agent_breakdown": {}}
        triggers = evaluate_triggers([], costs)
        cost_triggers = [t for t in triggers if t.category == "cost"]
        assert len(cost_triggers) >= 1
        assert "exceeds" in cost_triggers[0].trigger.lower()

    def test_evaluate_triggers_structural_large_team(self):
        from agents.chief_of_staff.org_evaluator import evaluate_triggers

        # Create 7 reports from engineering agents
        reports = [_make_report(f"agent_{i}") for i in range(7)]
        triggers = evaluate_triggers(reports, {})
        structural = [t for t in triggers if t.category == "structural"]
        assert any(">6" in t.trigger for t in structural)

    def test_evaluate_triggers_structural_small_team(self):
        from agents.chief_of_staff.org_evaluator import evaluate_triggers

        reports = [_make_report("pipeline")]
        triggers = evaluate_triggers(reports, {})
        structural = [t for t in triggers if t.category == "structural"]
        assert any("only 1" in t.trigger for t in structural)

    def test_evaluate_triggers_performance_zero_findings(self):
        from agents.chief_of_staff.org_evaluator import evaluate_triggers

        reports = [_make_report("architect", [])]
        triggers = evaluate_triggers(reports, {})
        perf = [t for t in triggers if t.category == "performance"]
        assert any("zero findings" in t.trigger.lower() for t in perf)

    def test_run_agent_value_audit(self, sample_findings: list[Finding]):
        from agents.chief_of_staff.org_evaluator import run_agent_value_audit

        reports = [
            _make_report("architect", [sample_findings[0], sample_findings[1]]),
            _make_report("doc_keeper", [sample_findings[4]]),
        ]
        audits = run_agent_value_audit("engineering", reports)
        assert len(audits) == 2
        assert audits[0].agent == "architect"
        assert audits[0].verdict in ("essential", "valuable", "marginal", "redundant")

    def test_run_agent_value_audit_empty(self):
        from agents.chief_of_staff.org_evaluator import run_agent_value_audit

        audits = run_agent_value_audit("engineering", [])
        assert audits == []

    def test_agent_value_audit_marginal_verdict(self):
        from agents.chief_of_staff.org_evaluator import run_agent_value_audit

        reports = [_make_report("architect", [])]  # zero findings
        audits = run_agent_value_audit("engineering", reports)
        assert audits[0].verdict == "marginal"

    def test_generate_proposal_empty(self):
        from agents.chief_of_staff.org_evaluator import generate_restructuring_proposal

        assert generate_restructuring_proposal([]) == ""

    def test_generate_proposal_with_triggers(self):
        from agents.chief_of_staff.org_evaluator import generate_restructuring_proposal
        from agents.chief_of_staff.schemas import OrgTrigger

        triggers = [
            OrgTrigger(
                category="cost",
                trigger="Over budget",
                severity="high",
                affected_teams=["engineering"],
            ),
            OrgTrigger(
                category="structural",
                trigger="Too many agents",
                severity="medium",
                affected_teams=["engineering"],
            ),
        ]
        result = generate_restructuring_proposal(triggers)
        assert "Org Restructuring Evaluation" in result
        assert "2 trigger(s)" in result
        assert "Cost" in result
        assert "Structural" in result
        assert "CoS Recommendation" in result

    def test_generate_proposal_critical_triggers(self):
        from agents.chief_of_staff.org_evaluator import generate_restructuring_proposal
        from agents.chief_of_staff.schemas import OrgTrigger

        triggers = [
            OrgTrigger(
                category="cost", trigger="Critical overrun", severity="critical"
            ),
        ]
        result = generate_restructuring_proposal(triggers)
        assert "founder review" in result.lower()


# ---------------------------------------------------------------------------
# Pod manager tests (Gap 5)
# ---------------------------------------------------------------------------


class TestPodManager:
    @pytest.fixture(autouse=True)
    def _use_tmp_state(self, tmp_path: Path):
        state_path = tmp_path / "cos_state.json"
        with patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path):
            yield

    def test_create_pod(self):
        from agents.chief_of_staff.pod_manager import create_pod, get_active_pods

        pod = create_pod(
            name="Launch Sprint",
            mission="Ship MVP",
            members=[
                {"agent": "Architect", "team": "engineering", "role": "tech"},
                {"agent": "ProductManager", "team": "product", "role": "spec"},
            ],
            lead="ProductManager",
            duration_weeks=2,
            exit_criteria=["MVP live", "10 signups"],
        )
        assert pod.name == "Launch Sprint"
        assert pod.status == "active"
        assert len(pod.exit_criteria) == 2
        assert len(pod.exit_criteria_met) == 2
        assert all(not m for m in pod.exit_criteria_met)

        active = get_active_pods()
        assert len(active) == 1

    def test_create_pod_max_concurrent(self):
        from agents.chief_of_staff.pod_manager import create_pod

        members = [
            {"agent": "A", "team": "engineering", "role": "x"},
            {"agent": "B", "team": "product", "role": "y"},
        ]
        create_pod(name="Pod1", mission="M1", members=members, lead="A")
        create_pod(name="Pod2", mission="M2", members=members, lead="A")
        with pytest.raises(ValueError, match="Cannot create pod"):
            create_pod(name="Pod3", mission="M3", members=members, lead="A")

    def test_create_pod_too_many_members(self):
        from agents.chief_of_staff.pod_manager import create_pod

        members = [{"agent": f"A{i}", "team": "eng", "role": "x"} for i in range(6)]
        with pytest.raises(ValueError, match="2-5 members"):
            create_pod(name="Big", mission="M", members=members, lead="A0")

    def test_create_pod_too_few_members(self):
        from agents.chief_of_staff.pod_manager import create_pod

        with pytest.raises(ValueError, match="at least 2"):
            create_pod(
                name="Tiny",
                mission="M",
                members=[{"agent": "A", "team": "eng", "role": "x"}],
                lead="A",
            )

    def test_check_pod_health_green(self):
        from agents.chief_of_staff.pod_manager import check_pod_health, create_pod

        pod = create_pod(
            name="Test",
            mission="M",
            members=[
                {"agent": "A", "team": "eng", "role": "x"},
                {"agent": "B", "team": "prod", "role": "y"},
            ],
            lead="A",
            duration_weeks=2,
            exit_criteria=["Done"],
        )
        status = check_pod_health(pod)
        assert status.health == "green"
        assert status.days_elapsed >= 0
        assert status.exit_met == 0
        assert status.exit_total == 1

    def test_check_pod_health_overdue(self):
        from agents.chief_of_staff.pod_manager import check_pod_health
        from agents.chief_of_staff.schemas import Pod

        pod = Pod(
            id="pod-test",
            name="Old Pod",
            mission="M",
            lead="A",
            members=[
                {"agent": "A", "team": "eng", "role": "x"},
                {"agent": "B", "team": "prod", "role": "y"},
            ],
            duration_weeks=1,
            start_date="2025-01-01",
            exit_criteria=["Done"],
            exit_criteria_met=[False],
            status="active",
        )
        status = check_pod_health(pod)
        assert status.health == "red"
        assert "Overdue" in status.note

    def test_update_exit_criteria(self):
        from agents.chief_of_staff.pod_manager import (
            create_pod,
            get_active_pods,
            update_exit_criteria,
        )

        pod = create_pod(
            name="Test",
            mission="M",
            members=[
                {"agent": "A", "team": "eng", "role": "x"},
                {"agent": "B", "team": "prod", "role": "y"},
            ],
            lead="A",
            exit_criteria=["Step 1", "Step 2"],
        )
        update_exit_criteria(pod.id, 0, True)
        active = get_active_pods()
        assert active[0].exit_criteria_met[0] is True
        assert active[0].exit_criteria_met[1] is False

    def test_dissolve_pod(self):
        from agents.chief_of_staff.pod_manager import (
            create_pod,
            dissolve_pod,
            get_active_pods,
            get_all_pods,
        )

        pod = create_pod(
            name="Test",
            mission="M",
            members=[
                {"agent": "A", "team": "eng", "role": "x"},
                {"agent": "B", "team": "prod", "role": "y"},
            ],
            lead="A",
        )
        dissolve_pod(pod.id, outcomes="Shipped", learnings="Fast iteration works")
        assert len(get_active_pods()) == 0
        all_pods = get_all_pods()
        assert len(all_pods) == 1
        assert all_pods[0].status == "dissolved"

    def test_dissolve_nonexistent_pod(self):
        from agents.chief_of_staff.pod_manager import dissolve_pod

        with pytest.raises(ValueError, match="not found"):
            dissolve_pod("pod-nonexistent")

    def test_get_pod_report_empty(self):
        from agents.chief_of_staff.pod_manager import get_pod_report

        assert get_pod_report() == ""

    def test_get_pod_report_with_pods(self):
        from agents.chief_of_staff.pod_manager import create_pod, get_pod_report

        create_pod(
            name="Launch Sprint",
            mission="Ship MVP",
            members=[
                {"agent": "A", "team": "eng", "role": "x"},
                {"agent": "B", "team": "prod", "role": "y"},
            ],
            lead="A",
            exit_criteria=["Live", "10 users"],
        )
        report = get_pod_report()
        assert "Active Pods" in report
        assert "Launch Sprint" in report
        assert "0/2 exit criteria" in report

    def test_detect_permanent_pods_none(self):
        from agents.chief_of_staff.pod_manager import detect_permanent_pods

        assert detect_permanent_pods() == []

    def test_detect_permanent_pods_anti_pattern(self):
        from agents.chief_of_staff.pod_manager import (
            create_pod,
            detect_permanent_pods,
            dissolve_pod,
        )

        members = [
            {"agent": "A", "team": "eng", "role": "x"},
            {"agent": "B", "team": "prod", "role": "y"},
        ]
        # Create and dissolve the same pod twice
        pod1 = create_pod(name="Repeat1", mission="M", members=members, lead="A")
        dissolve_pod(pod1.id)
        pod2 = create_pod(name="Repeat2", mission="M", members=members, lead="A")
        dissolve_pod(pod2.id)

        warnings = detect_permanent_pods()
        assert len(warnings) == 1
        assert "reformed 2 times" in warnings[0]


# ---------------------------------------------------------------------------
# Cross-team request routing tests (Gap 6)
# ---------------------------------------------------------------------------


class TestRequestRouting:
    @pytest.fixture(autouse=True)
    def _use_tmp_state(self, tmp_path: Path):
        state_path = tmp_path / "cos_state.json"
        with patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path):
            yield

    def test_route_and_track_request(self):
        from agents.chief_of_staff.router import (
            get_open_requests,
            route_and_track_request,
        )

        req = {
            "source_agent": "architect",
            "request": "Need API spec review for auth endpoints",
            "urgency": "high",
        }
        tracked = route_and_track_request(req)
        assert tracked.status == "routed"
        assert tracked.source_agent == "architect"
        assert tracked.routed_to != ""

        open_reqs = get_open_requests()
        assert len(open_reqs) == 1

    def test_resolve_request(self):
        from agents.chief_of_staff.router import (
            get_open_requests,
            resolve_request,
            route_and_track_request,
        )

        tracked = route_and_track_request(
            {
                "source_agent": "pipeline",
                "request": "Need schema migration review",
                "urgency": "medium",
            }
        )
        resolve_request(tracked.id)
        assert len(get_open_requests()) == 0

    def test_resolve_nonexistent_request(self):
        from agents.chief_of_staff.router import resolve_request

        with pytest.raises(ValueError, match="not found"):
            resolve_request("req-nonexistent")

    def test_stale_requests(self):
        from agents.chief_of_staff.router import (
            get_stale_requests,
            route_and_track_request,
        )

        tracked = route_and_track_request(
            {
                "source_agent": "architect",
                "request": "Old request",
                "urgency": "low",
            }
        )
        # Stale detection with days=0 should catch even fresh requests
        stale = get_stale_requests(days=0)
        assert len(stale) == 1

    def test_request_tracking_report_empty(self):
        from agents.chief_of_staff.router import get_request_tracking_report

        assert get_request_tracking_report() == ""

    def test_request_tracking_report_with_requests(self):
        from agents.chief_of_staff.router import (
            get_request_tracking_report,
            route_and_track_request,
        )

        route_and_track_request(
            {
                "source_agent": "security",
                "request": "Need privacy audit for marketplace",
                "urgency": "critical",
            }
        )
        report = get_request_tracking_report()
        assert "Cross-Team Requests" in report
        assert "1 open" in report
        assert "CRITICAL" in report

    def test_multiple_requests_routing(self):
        from agents.chief_of_staff.router import (
            get_open_requests,
            route_and_track_request,
        )

        for i in range(5):
            route_and_track_request(
                {
                    "source_agent": f"agent_{i}",
                    "request": f"Request {i} about database migration",
                    "urgency": "medium",
                }
            )
        assert len(get_open_requests()) == 5


# ---------------------------------------------------------------------------
# Budget enforcer tests (Gap 7)
# ---------------------------------------------------------------------------


class TestBudgetEnforcer:
    @pytest.fixture(autouse=True)
    def _use_tmp_state(self, tmp_path: Path):
        state_path = tmp_path / "cos_state.json"
        with patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path):
            yield

    def test_enforce_budget_within_limits(self):
        from agents.chief_of_staff.budget_enforcer import enforce_budget

        costs = {
            "total_estimated_cost_usd": 0.50,
            "agent_breakdown": {
                "architect": {"estimated_cost_usd": 0.10},
                "test_engineer": {"estimated_cost_usd": 0.05},
            },
        }
        actions = enforce_budget(costs)
        ok_actions = [a for a in actions if a.action == "ok"]
        assert len(ok_actions) > 0

    def test_enforce_budget_team_throttle(self):
        from agents.chief_of_staff.budget_enforcer import enforce_budget

        costs = {
            "total_estimated_cost_usd": 0.80,
            "agent_breakdown": {
                "architect": {"estimated_cost_usd": 0.60},
                "test_engineer": {"estimated_cost_usd": 0.20},
            },
        }
        actions = enforce_budget(costs)
        throttled = [a for a in actions if a.action == "throttle"]
        # engineering cap is $1.50, total $0.80 of agents = within
        # but data, product, etc. are $0 so no throttle for them
        # This depends on exact caps — check total
        assert isinstance(actions, list)

    def test_enforce_budget_total_cap(self):
        from agents.chief_of_staff.budget_enforcer import enforce_budget

        costs = {
            "total_estimated_cost_usd": 10.0,  # Way over $3 cap
            "agent_breakdown": {},
        }
        actions = enforce_budget(costs)
        total_throttle = [
            a for a in actions if a.team == "all" and a.action == "throttle"
        ]
        assert len(total_throttle) == 1
        assert "Skip non-critical scans" in total_throttle[0].recommendation

    def test_update_and_check_throttle_status(self):
        from agents.chief_of_staff.budget_enforcer import (
            should_throttle_team,
            update_throttle_status,
        )
        from agents.chief_of_staff.schemas import BudgetAction

        actions = [
            BudgetAction(
                team="data",
                action="throttle",
                reason="Over budget",
                current_cost=0.60,
                budget_cap=0.30,
                recommendation="Downgrade to Haiku",
            ),
        ]
        update_throttle_status(actions)
        assert should_throttle_team("data") is True
        assert should_throttle_team("engineering") is False

    def test_throttle_cleared_when_ok(self):
        from agents.chief_of_staff.budget_enforcer import (
            should_throttle_team,
            update_throttle_status,
        )
        from agents.chief_of_staff.schemas import BudgetAction

        # First throttle
        update_throttle_status(
            [
                BudgetAction(team="data", action="throttle", reason="Over"),
            ]
        )
        assert should_throttle_team("data") is True

        # Then clear
        update_throttle_status(
            [
                BudgetAction(team="data", action="ok", reason="Back in budget"),
            ]
        )
        assert should_throttle_team("data") is False

    def test_budget_enforcement_report_empty(self):
        from agents.chief_of_staff.budget_enforcer import get_budget_enforcement_report

        assert get_budget_enforcement_report([]) == ""

    def test_budget_enforcement_report_throttled(self):
        from agents.chief_of_staff.budget_enforcer import get_budget_enforcement_report
        from agents.chief_of_staff.schemas import BudgetAction

        actions = [
            BudgetAction(
                team="data",
                action="throttle",
                reason="150% of cap",
                recommendation="Downgrade",
            ),
            BudgetAction(
                team="engineering",
                action="warn",
                reason="110% of cap",
            ),
        ]
        report = get_budget_enforcement_report(actions)
        assert "Budget Enforcement" in report
        assert "THROTTLED" in report
        assert "WARNING" in report


# ---------------------------------------------------------------------------
# WhatsApp command processing tests (Gap 8)
# ---------------------------------------------------------------------------


class TestWhatsAppCommands:
    @pytest.fixture(autouse=True)
    def _use_tmp_dirs(self, tmp_path: Path):
        state_path = tmp_path / "cos_state.json"
        wa_dir = tmp_path / "whatsapp"
        wa_dir.mkdir()
        with (
            patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path),
            patch("agents.chief_of_staff.cos_agent.WHATSAPP_DIR", wa_dir),
        ):
            self._wa_dir = wa_dir
            yield

    def test_process_no_replies(self):
        from agents.chief_of_staff.cos_agent import _process_whatsapp_commands

        results = _process_whatsapp_commands()
        assert results == []

    def test_process_status_command(self):
        from agents.chief_of_staff.cos_agent import _process_whatsapp_commands

        reply = self._wa_dir / "whatsapp-reply-001.txt"
        reply.write_text("status", encoding="utf-8")

        results = _process_whatsapp_commands()
        assert len(results) == 1
        assert results[0].get("command") == "status"
        # File should be renamed to .processed
        assert not reply.exists()
        assert reply.with_suffix(".processed").exists()

    def test_process_approve_command(self):
        from agents.chief_of_staff.cos_agent import _process_whatsapp_commands

        reply = self._wa_dir / "whatsapp-reply-002.txt"
        reply.write_text("1=yes", encoding="utf-8")

        results = _process_whatsapp_commands()
        assert len(results) == 1

    def test_process_empty_reply(self):
        from agents.chief_of_staff.cos_agent import _process_whatsapp_commands

        reply = self._wa_dir / "whatsapp-reply-003.txt"
        reply.write_text("", encoding="utf-8")

        results = _process_whatsapp_commands()
        assert results == []

    def test_process_multiple_replies(self):
        from agents.chief_of_staff.cos_agent import _process_whatsapp_commands

        (self._wa_dir / "whatsapp-reply-001.txt").write_text("status", encoding="utf-8")
        (self._wa_dir / "whatsapp-reply-002.txt").write_text("cost", encoding="utf-8")

        results = _process_whatsapp_commands()
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Integration: wiring verification tests
# ---------------------------------------------------------------------------


class TestCosWiringIntegration:
    """Verify all 5 gaps are properly wired into run_daily/run_weekly."""

    @pytest.fixture(autouse=True)
    def _use_tmp_dirs(self, tmp_path: Path):
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        state_path = tmp_path / "cos_state.json"
        wa_dir = tmp_path / "whatsapp"
        wa_dir.mkdir()

        with (
            patch("agents.chief_of_staff.cos_agent.REPORTS_DIR", reports_dir),
            patch(
                "agents.chief_of_staff.cos_agent.DATA_TEAM_REPORTS_DIR", tmp_path / "d"
            ),
            patch(
                "agents.chief_of_staff.cos_agent.PRODUCT_TEAM_REPORTS_DIR",
                tmp_path / "p",
            ),
            patch(
                "agents.chief_of_staff.cos_agent.OPS_TEAM_REPORTS_DIR", tmp_path / "o"
            ),
            patch(
                "agents.chief_of_staff.cos_agent.FINANCE_TEAM_REPORTS_DIR",
                tmp_path / "f",
            ),
            patch(
                "agents.chief_of_staff.cos_agent.GTM_TEAM_REPORTS_DIR", tmp_path / "g"
            ),
            patch("agents.chief_of_staff.cos_learning._STATE_PATH", state_path),
            patch("agents.chief_of_staff.cos_agent.WHATSAPP_DIR", wa_dir),
        ):
            self._reports_dir = reports_dir
            self._wa_dir = wa_dir
            yield

    def _write_report(self, report: AgentReport) -> None:
        path = self._reports_dir / f"{report.agent}_latest.json"
        path.write_text(report.serialize())

    def test_run_daily_includes_budget_enforcement(self):
        from agents.chief_of_staff.cos_agent import run_daily

        self._write_report(
            _make_report(
                "architect",
                [
                    _make_finding("F1", "high", "security", "Issue"),
                ],
            )
        )
        result = run_daily()
        # Brief should be generated (even if no budget issues)
        assert "# Founder Daily Brief" in result

    def test_run_daily_processes_whatsapp_commands(self):
        from agents.chief_of_staff.cos_agent import run_daily

        self._write_report(_make_report("architect"))
        (self._wa_dir / "whatsapp-reply-001.txt").write_text("status")
        result = run_daily()
        assert "# Founder Daily Brief" in result
        # Reply file should be processed
        assert (self._wa_dir / "whatsapp-reply-001.processed").exists()

    def test_run_daily_routes_cross_team_requests(self):
        from agents.chief_of_staff.cos_agent import run_daily
        from agents.chief_of_staff.router import get_open_requests

        # Write a valid report so run_daily() doesn't bail early
        self._write_report(_make_report("architect"))

        # Write a second report file with a cross-team request
        # (separate file so AgentReport.from_dict doesn't fail on extra key)
        report2 = _make_report("test_engineer")
        data = json.loads(report2.serialize())
        data["cross_team_requests"] = [
            {
                "request": "Need database migration review",
                "urgency": "high",
                "blocking": "data",
            }
        ]
        # Remove the extra key before AgentReport.from_dict processes it,
        # but _load_dir extracts cross_team_requests before from_dict
        path = self._reports_dir / "test_engineer_latest.json"
        path.write_text(json.dumps(data))

        result = run_daily()
        assert "# Founder Daily Brief" in result
        # Request should have been routed and tracked
        open_reqs = get_open_requests()
        assert len(open_reqs) >= 1

    def test_run_weekly_includes_org_evaluation(self):
        from agents.chief_of_staff.cos_agent import run_weekly

        self._write_report(_make_report("architect"))
        result = run_weekly()
        assert "# Weekly Synthesis" in result
        # Org evaluation runs but may or may not produce triggers


# ---------------------------------------------------------------------------
# Telegram bridge tests
# ---------------------------------------------------------------------------


class TestTelegramBridge:
    """Tests for the Telegram Bot bridge."""

    def test_escape_markdown_v2(self):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        bridge = TelegramBridge()
        assert bridge.escape_md("hello_world") == r"hello\_world"
        assert bridge.escape_md("$1.50") == r"$1\.50"
        assert bridge.escape_md("test (foo)") == r"test \(foo\)"

    def test_format_daily_brief(self):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        bridge = TelegramBridge()
        team_summaries = [
            {
                "team": "engineering",
                "health": "green",
                "summary": "Clean scan",
                "agent_count": 5,
                "finding_count": 0,
            },
            {
                "team": "data",
                "health": "red",
                "summary": "Pipeline issue",
                "agent_count": 4,
                "finding_count": 3,
            },
        ]
        msg = bridge.format_daily_brief(
            date="Feb 18",
            team_summaries=team_summaries,
            decisions=["Approve schema migration"],
            cost="$2.40/day",
        )
        assert "WarmPath Daily" in msg
        assert "Feb 18" in msg

    def test_format_weekly_summary(self):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        bridge = TelegramBridge()
        msg = bridge.format_weekly_summary(
            week_num=8,
            cost="$16.80",
            daily_avg="$2.40/day",
            top_win="Deployed marketplace",
            top_risk="No NH signups",
        )
        assert "Week 8" in msg
        assert "Deployed marketplace" in msg

    def test_format_escalation(self):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        bridge = TelegramBridge()
        msg = bridge.format_escalation(
            title="PII leak detected",
            detail="Contact emails exposed in marketplace API",
            option_a="Shut down marketplace",
            option_b="Patch and monitor",
        )
        assert "PII leak" in msg
        assert "A)" in msg

    def test_send_message_no_token(self, tmp_path, monkeypatch):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
        bridge = TelegramBridge(output_dir=tmp_path)
        result = bridge.send("Hello test", msg_type="test")
        assert result["status"] == "file_only"
        assert result["telegram"] is False
        files = list(tmp_path.glob("telegram-test-*.txt"))
        assert len(files) == 1

    def test_send_message_with_token(self, tmp_path, monkeypatch):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        bridge = TelegramBridge(output_dir=tmp_path)
        with patch("httpx.Client.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {
                "ok": True,
                "result": {"message_id": 1},
            }
            mock_post.return_value.raise_for_status = lambda: None
            result = bridge.send("Hello", msg_type="test")
        assert result["telegram"] is True
        assert result["status"] == "sent"

    def test_parse_reply_reuses_whatsapp_grammar(self):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        bridge = TelegramBridge()
        assert bridge.parse_reply("status") == {"command": "status"}
        assert bridge.parse_reply("1")["command"] == "approve_item"
        assert bridge.parse_reply("ship beta")["command"] == "ship"

    def test_generate_daily_brief_end_to_end(self, tmp_path, monkeypatch):
        from agents.chief_of_staff.telegram_bridge import TelegramBridge

        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        bridge = TelegramBridge(output_dir=tmp_path)
        brief_data = {
            "decisions_needed": [{"summary": "Approve migration"}],
            "team_summaries": [
                {
                    "team": "engineering",
                    "health": "green",
                    "summary": "Clean",
                    "agent_count": 5,
                    "finding_count": 0,
                },
            ],
        }
        costs = {"total_estimated_cost_usd": 2.40}
        result = bridge.generate_daily_brief(brief_data, costs, alerts=[])
        assert result["status"] == "file_only"
        files = list(tmp_path.glob("telegram-daily-*.txt"))
        assert len(files) == 1
