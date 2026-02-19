"""Tests for Monetization scanner enhancements — pricing benchmarks, positioning, experiments.

Verifies:
- _benchmark_pricing produces benchmark data + insights
- _analyze_pricing_position produces positioning insights
- _design_experiments produces PricingExperiment objects
- Graceful handling when web_search returns empty results
- New metrics/insights appear in scan() report
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import patch


class TestBenchmarkPricing:
    """External pricing benchmark collection from web search."""

    def test_produces_benchmark_metrics(self):
        from agents.shared.report import Finding
        from agents.shared.web_tools import SearchResult
        from gtm_team.shared.report import MarketInsight
        from gtm_team.monetization.scanner import _benchmark_pricing

        mock_results = [
            SearchResult(
                title="Pricing Page",
                url="https://example.com",
                snippet="Plans start at $29/month with a free tier available",
            )
        ]
        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch(
            "gtm_team.monetization.scanner.web_search", return_value=mock_results
        ):
            _benchmark_pricing(findings, insights, metrics)

        assert "pricing_benchmarks" in metrics
        assert "benchmark_companies_scanned" in metrics
        assert metrics["benchmark_companies_scanned"] == 12
        assert len(insights) >= 1
        assert any(i.id == "monet-insight-benchmarks" for i in insights)

    def test_extracts_price_points(self):
        from agents.shared.report import Finding
        from agents.shared.web_tools import SearchResult
        from gtm_team.shared.report import MarketInsight
        from gtm_team.monetization.scanner import _benchmark_pricing

        mock_results = [
            SearchResult(
                title="Pricing",
                url="https://example.com",
                snippet="Basic plan $19/mo, Pro plan $49/mo, Enterprise $99/mo",
            )
        ]
        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch(
            "gtm_team.monetization.scanner.web_search", return_value=mock_results
        ):
            _benchmark_pricing(findings, insights, metrics)

        assert "benchmark_avg_price" in metrics
        assert "warmpath_pricing_percentile" in metrics

    def test_empty_web_results_graceful(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.monetization.scanner import _benchmark_pricing

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.monetization.scanner.web_search", return_value=[]):
            _benchmark_pricing(findings, insights, metrics)

        assert metrics["benchmark_companies_scanned"] == 12
        assert "benchmark_avg_price" not in metrics  # no prices extracted
        assert len(insights) >= 1


class TestAnalyzePricingPosition:
    """Pricing position analysis based on benchmark data."""

    def test_below_average_position(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.monetization.scanner import _analyze_pricing_position

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {
            "benchmark_avg_price": 45.0,
            "warmpath_pricing_percentile": 25.0,
            "benchmark_companies_scanned": 12,
        }

        _analyze_pricing_position(findings, insights, metrics)

        assert metrics["pricing_position"] == "below average"
        assert any(i.id == "monet-insight-position" for i in insights)

    def test_insufficient_data(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.monetization.scanner import _analyze_pricing_position

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {"benchmark_companies_scanned": 12}

        _analyze_pricing_position(findings, insights, metrics)

        assert metrics["pricing_position"] == "insufficient_data"
        assert len(insights) >= 1


class TestDesignExperiments:
    """Pricing experiment design."""

    def test_produces_experiments(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import PricingExperiment
        from gtm_team.monetization.scanner import _design_experiments

        findings: list[Finding] = []
        experiments: list[PricingExperiment] = []
        metrics: dict = {}

        _design_experiments(findings, experiments, metrics)

        assert len(experiments) == 2
        assert metrics["experiments_designed"] == 2
        assert experiments[0].id == "exp-price-tiers"
        assert experiments[1].id == "exp-annual-discount"
        assert experiments[0].status == "designed"

    def test_experiment_has_metrics_to_track(self):
        from agents.shared.report import Finding
        from gtm_team.shared.report import PricingExperiment
        from gtm_team.monetization.scanner import _design_experiments

        findings: list[Finding] = []
        experiments: list[PricingExperiment] = []
        metrics: dict = {}

        _design_experiments(findings, experiments, metrics)

        for exp in experiments:
            assert len(exp.metrics_to_track) > 0


class TestMonetizationScanIntegration:
    """Full scan() includes new benchmark and experiment data."""

    def test_scan_includes_benchmarks(self):
        from gtm_team.monetization.scanner import scan

        with patch("gtm_team.monetization.scanner.web_search", return_value=[]):
            report = scan()

        assert "benchmark_companies_scanned" in report.metrics
        assert "pricing_benchmarks" in report.metrics

    def test_scan_includes_experiments(self):
        from gtm_team.monetization.scanner import scan

        with patch("gtm_team.monetization.scanner.web_search", return_value=[]):
            report = scan()

        assert len(report.pricing_experiments) >= 2
        assert report.metrics.get("experiments_designed", 0) >= 2

    def test_scan_includes_pricing_position(self):
        from gtm_team.monetization.scanner import scan

        with patch("gtm_team.monetization.scanner.web_search", return_value=[]):
            report = scan()

        assert "pricing_position" in report.metrics
