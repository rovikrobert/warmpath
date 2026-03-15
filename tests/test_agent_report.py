"""Tests for AgentReport serialization and deserialization."""

import logging

from agents.shared.report import AgentReport, Finding


def test_from_dict_ignores_unknown_fields():
    """AgentReport.from_dict() should silently drop fields not in the dataclass."""
    data = {
        "agent": "data_lead",
        "timestamp": "2026-03-01T00:00:00",
        "scan_duration_seconds": 1.5,
        "findings": [
            {
                "id": "F1",
                "severity": "medium",
                "category": "data_quality",
                "title": "Stale enrichment cache",
                "detail": "Cache miss rate exceeded threshold",
            }
        ],
        "metrics": {"cache_hit_rate": 0.85},
        "insights": [{"type": "trend", "note": "improving"}],
        "kpi_snapshots": [{"metric": "coverage", "value": 92}],
        "cross_team_requests": [{"target": "engineering", "urgency": 3}],
    }
    report = AgentReport.from_dict(data)
    assert report.agent == "data_lead"
    assert len(report.findings) == 1
    assert report.findings[0].title == "Stale enrichment cache"
    assert report.metrics == {"cache_hit_rate": 0.85}


def test_from_dict_handles_product_team_fields():
    """Product team reports include product_insights, ux_findings, design_findings."""
    data = {
        "agent": "product_lead",
        "findings": [],
        "product_insights": [{"area": "onboarding"}],
        "ux_findings": [],
        "design_findings": [],
    }
    report = AgentReport.from_dict(data)
    assert report.agent == "product_lead"


def test_from_dict_handles_finance_team_fields():
    """Finance team reports include financial_findings, credit_findings, etc."""
    data = {
        "agent": "finance_lead",
        "findings": [],
        "financial_findings": [{"metric": "burn_rate"}],
        "credit_findings": [],
        "compliance_findings": [{"regulation": "PDPA", "deadline": "2026-06-01"}],
        "cost_snapshots": [],
    }
    report = AgentReport.from_dict(data)
    assert report.agent == "finance_lead"


def test_from_dict_handles_ops_and_gtm_insights():
    """Ops and GTM team reports include ops_insights and market_insights."""
    for agent, extra in [
        ("ops_lead", {"ops_insights": [{"area": "coaching"}]}),
        ("gtm_lead", {"market_insights": [{"competitor": "Refer.me"}]}),
    ]:
        data = {"agent": agent, "findings": [], **extra}
        report = AgentReport.from_dict(data)
        assert report.agent == agent


def test_from_dict_does_not_mutate_input():
    """from_dict should not modify the input dict."""
    data = {
        "agent": "test",
        "findings": [
            {
                "id": "F1",
                "severity": "low",
                "category": "t",
                "title": "t",
                "detail": "d",
            }
        ],
        "extra_field": "should_survive",
    }
    original_keys = set(data.keys())
    AgentReport.from_dict(data)
    assert set(data.keys()) == original_keys
    assert "findings" in data  # Should NOT be popped from original


def test_round_trip_serialization():
    """to_dict -> from_dict preserves all standard fields."""
    original = AgentReport(
        agent="test",
        findings=[
            Finding(
                id="F1",
                severity="high",
                category="security",
                title="SQL injection",
                detail="Unparameterized query",
            )
        ],
        metrics={"coverage": 85},
        learning_updates=["New pattern detected"],
    )
    data = original.to_dict()
    restored = AgentReport.from_dict(data)
    assert restored.agent == original.agent
    assert len(restored.findings) == 1
    assert restored.findings[0].title == "SQL injection"
    assert restored.metrics == {"coverage": 85}


def test_agent_report_warns_on_empty_recommendation(caplog):
    """AgentReport.__post_init__ logs warning for findings with empty recommendations."""
    findings = [
        Finding(
            id="F1",
            severity="high",
            category="security",
            title="SQL injection",
            detail="Unparameterized query",
            recommendation="",
        ),
        Finding(
            id="F2",
            severity="low",
            category="style",
            title="Minor style",
            detail="Indentation",
            recommendation="Fix indentation in app/api/search.py:42",
        ),
    ]
    with caplog.at_level(logging.WARNING, logger="agents.shared.report"):
        AgentReport(agent="test", findings=findings)
    assert "F1" in caplog.text
    assert "empty recommendation" in caplog.text.lower()


def test_finding_actionable_recommendation_format():
    """Recommendation should follow 'do X in Y because Z' format when populated."""
    f = Finding(
        id="F1",
        severity="high",
        category="security",
        title="SQL injection",
        detail="d",
        recommendation="Parameterize query in app/api/search.py:42. Convention: no raw SQL (CLAUDE.md)",
    )
    assert len(f.recommendation) > 10
    assert f.recommendation != ""
