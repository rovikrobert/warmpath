"""Tests for Marketing scanner enhancements — analytics, conversion funnel, SEO readiness.

Verifies:
- _check_analytics_integration detects PostHog and trackEvent usage
- _check_conversion_funnel detects funnel events in frontend code
- _check_seo_readiness detects SEO signals in index.html
- Graceful handling when files don't exist
- New metrics/insights appear in scan() report
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import patch


class TestCheckAnalyticsIntegration:
    """PostHog analytics integration detection."""

    def test_detects_no_posthog(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_analytics_integration

        # Create a minimal main.jsx without PostHog
        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "main.jsx").write_text(
            "import React from 'react';\nReactDOM.render(<App />, root);"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_analytics_integration(findings, insights, metrics)

        assert metrics["posthog_initialized"] is False
        assert any(f.id == "MKT-NO-ANALYTICS" for f in findings)
        assert any(i.id == "mkt-insight-analytics" for i in insights)

    def test_detects_posthog_present(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_analytics_integration

        (tmp_path / "frontend" / "src").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "main.jsx").write_text(
            "import posthog from 'posthog-js';\nposthog.init('key');"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_analytics_integration(findings, insights, metrics)

        assert metrics["posthog_initialized"] is True
        assert not any(f.id == "MKT-NO-ANALYTICS" for f in findings)

    def test_counts_tracked_pages(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_analytics_integration

        (tmp_path / "frontend" / "src" / "pages").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "main.jsx").write_text("// no posthog")
        (tmp_path / "frontend" / "src" / "pages" / "Home.jsx").write_text(
            "trackEvent('page_view')"
        )
        (tmp_path / "frontend" / "src" / "pages" / "About.jsx").write_text(
            "no tracking here"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_analytics_integration(findings, insights, metrics)

        assert metrics["pages_with_tracking"] == 1


class TestCheckConversionFunnel:
    """Conversion funnel event tracking detection."""

    def test_detects_missing_events(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_conversion_funnel

        (tmp_path / "frontend" / "src" / "pages").mkdir(parents=True)
        (tmp_path / "frontend" / "src" / "pages" / "Auth.jsx").write_text(
            "signup_completed and email_verified tracked here"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_conversion_funnel(findings, insights, metrics)

        assert metrics["funnel_events_tracked"] == 2
        assert len(metrics["funnel_events_missing"]) == 4
        assert any(f.id == "MKT-FUNNEL-GAPS" for f in findings)
        assert any(i.id == "mkt-insight-funnel" for i in insights)

    def test_no_frontend_graceful(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_conversion_funnel

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_conversion_funnel(findings, insights, metrics)

        assert metrics["funnel_events_tracked"] == 0
        assert len(metrics["funnel_events_missing"]) == 6


class TestCheckSeoReadiness:
    """Extended SEO readiness detection."""

    def test_detects_missing_signals(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_seo_readiness

        (tmp_path / "frontend").mkdir(parents=True)
        (tmp_path / "frontend" / "index.html").write_text("<html><head></head></html>")

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_seo_readiness(findings, insights, metrics)

        assert "seo_signals" in metrics
        assert metrics["seo_score"] == 0.0
        assert any(f.id == "MKT-SEO-GAPS" for f in findings)
        assert any(i.id == "mkt-insight-seo" for i in insights)

    def test_detects_present_signals(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.marketing.scanner import _check_seo_readiness

        (tmp_path / "frontend" / "public").mkdir(parents=True)
        (tmp_path / "frontend" / "index.html").write_text(
            '<html><head><meta name="description" content="test">'
            '<meta property="og:title" content="t">'
            '<link rel="canonical" href="/">'
            "</head></html>"
        )
        (tmp_path / "frontend" / "public" / "robots.txt").write_text("User-agent: *")
        (tmp_path / "frontend" / "public" / "sitemap.xml").write_text("<urlset/>")

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.marketing.scanner.PROJECT_ROOT", tmp_path):
            _check_seo_readiness(findings, insights, metrics)

        assert metrics["seo_score"] == 100.0
        assert not any(f.id == "MKT-SEO-GAPS" for f in findings)


class TestMarketingScanIntegration:
    """Full scan() includes new analytics, funnel, and SEO metrics."""

    def test_scan_includes_analytics_metrics(self):
        from gtm_team.marketing.scanner import scan

        with patch("gtm_team.marketing.scanner.web_search", return_value=[]):
            report = scan()

        assert "posthog_initialized" in report.metrics
        assert "pages_with_tracking" in report.metrics

    def test_scan_includes_funnel_metrics(self):
        from gtm_team.marketing.scanner import scan

        with patch("gtm_team.marketing.scanner.web_search", return_value=[]):
            report = scan()

        assert "funnel_events_tracked" in report.metrics
        assert "funnel_events_missing" in report.metrics

    def test_scan_includes_seo_metrics(self):
        from gtm_team.marketing.scanner import scan

        with patch("gtm_team.marketing.scanner.web_search", return_value=[]):
            report = scan()

        assert "seo_signals" in report.metrics
        assert "seo_score" in report.metrics
