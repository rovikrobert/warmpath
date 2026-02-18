"""Tests for StratOps scanner enhancements — competitive feature analysis and threat levels.

Verifies:
- _analyze_competitor_features produces comparison matrix + insights
- _assess_threat_levels produces threat assessment + insights
- Graceful handling when web_search returns empty results
- New metrics/insights appear in scan() report
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import patch



class TestAnalyzeCompetitorFeatures:
    """Feature comparison matrix from web search results."""

    def test_produces_comparison_matrix(self):
        from agents.shared.report import Finding
        from agents.shared.web_tools import SearchResult
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _analyze_competitor_features

        mock_results = [
            SearchResult(
                title="Competitor Features",
                url="https://example.com",
                snippet="csv upload and ai matching platform with analytics dashboard",
            )
        ]
        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.stratops.scanner.web_search", return_value=mock_results):
            _analyze_competitor_features(findings, insights, metrics)

        assert "comparison_matrix" in metrics
        assert "competitors_analyzed" in metrics
        assert metrics["competitors_analyzed"] == 5
        assert len(insights) >= 1
        assert any(i.id == "strat-insight-features" for i in insights)

    def test_empty_web_results_graceful(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _analyze_competitor_features

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.stratops.scanner.web_search", return_value=[]):
            _analyze_competitor_features(findings, insights, metrics)

        assert metrics["competitors_analyzed"] == 5
        assert metrics["comparison_matrix"] is not None
        assert len(insights) >= 1

    def test_featu[RESEND_KEY_REDACTED](self):
        from agents.shared.report import Finding
        from agents.shared.web_tools import SearchResult
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _analyze_competitor_features

        mock_results = [
            SearchResult(
                title="Features",
                url="https://example.com",
                snippet="referral tracking, mobile app, browser extension, api access",
            )
        ]
        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.stratops.scanner.web_search", return_value=mock_results):
            _analyze_competitor_features(findings, insights, metrics)

        matrix = metrics["comparison_matrix"]
        # At least one competitor should have detected features
        all_features_found = set()
        for comp_features in matrix.values():
            for feat, present in comp_features.items():
                if present:
                    all_features_found.add(feat)

        assert len(all_features_found) > 0


class TestAssessThreatLevels:
    """Threat level assessment for tracked competitors."""

    def test_produces_threat_assessment(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _assess_threat_levels

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        _assess_threat_levels(findings, insights, metrics)

        assert "threat_assessment" in metrics
        threat = metrics["threat_assessment"]
        assert len(threat) > 0

        # Each competitor should have scores, total, and level
        for comp_name, data in threat.items():
            assert "scores" in data
            assert "total" in data
            assert "level" in data
            assert data["level"] in ("critical", "high", "medium", "low")

    def test_linkedin_has_high_funding_score(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _assess_threat_levels

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        _assess_threat_levels(findings, insights, metrics)

        linkedin_data = metrics["threat_assessment"].get("LinkedIn")
        assert linkedin_data is not None
        assert linkedin_data["scores"]["funding_resources"] == 20

    def test_high_threats_produce_insight(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.stratops.scanner import _assess_threat_levels

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        _assess_threat_levels(findings, insights, metrics)

        # LinkedIn should be a high threat (20+18+20+8+5 = 71 -> critical or high)
        threat_insight = [i for i in insights if i.id == "strat-insight-threats"]
        assert len(threat_insight) >= 1


class TestStratOpsScanIntegration:
    """Full scan() includes new competitive analysis metrics."""

    def test_scan_includes_comparison_matrix(self):
        from gtm_team.stratops.scanner import scan

        with patch("gtm_team.stratops.scanner.web_search", return_value=[]):
            report = scan()

        assert "comparison_matrix" in report.metrics
        assert "competitors_analyzed" in report.metrics

    def test_scan_includes_threat_assessment(self):
        from gtm_team.stratops.scanner import scan

        with patch("gtm_team.stratops.scanner.web_search", return_value=[]):
            report = scan()

        assert "threat_assessment" in report.metrics
        assert len(report.metrics["threat_assessment"]) > 0
