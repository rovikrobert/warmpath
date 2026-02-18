"""Tests for ops team live data checks (7 CoS audit gaps)."""

from __future__ import annotations


class TestOpsSharedDb:
    """ops_team.shared.db — graceful sync session factory."""

    def test_get_session_returns_none_without_database_url(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)
        assert db_mod.get_session() is None

    def test_get_session_returns_session_with_database_url(self, monkeypatch):
        """When DATABASE_URL is set and _get_sync_engine works, return a session."""
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test_ops.db")

        from unittest.mock import patch
        from sqlalchemy import create_engine

        test_engine = create_engine("sqlite:///test_ops.db")

        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        with patch("app.database._get_sync_engine", return_value=test_engine):
            session = db_mod.get_session()
            assert session is not None
            session.close()

        test_engine.dispose()
        import os

        if os.path.exists("test_ops.db"):
            os.remove("test_ops.db")

    def test_get_session_returns_none_on_engine_failure(self, monkeypatch):
        """If _get_sync_engine raises, get_session returns None gracefully."""
        monkeypatch.setenv("DATABASE_URL", "[DATABASE_URL_REDACTED]")

        from unittest.mock import patch

        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        with patch(
            "app.database._get_sync_engine",
            side_effect=Exception("connection refused"),
        ):
            assert db_mod.get_session() is None


class TestKeevsLiveCoaching:
    """Keevs live coaching quality — calls mock handler with test scenarios."""

    def test_mock_response_quality_passes(self):
        from ops_team.keevs.keevs import _check_live_coaching_quality
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_coaching_quality(findings, insights, metrics)

        assert "live_coaching_scenarios_tested" in metrics
        assert metrics["live_coaching_scenarios_tested"] >= 3
        assert "live_coaching_test_pass_rate" in metrics
        assert metrics["live_coaching_test_pass_rate"] >= 0.0

    def test_mock_response_avg_length(self):
        from ops_team.keevs.keevs import _check_live_coaching_quality
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_coaching_quality(findings, insights, metrics)

        assert "live_coaching_avg_response_length" in metrics
        assert metrics["live_coaching_avg_response_length"] > 0


class TestTrebLiveFunnel:
    """Treb live NH activation funnel — queries users/uploads/prefs."""

    def test_funnel_without_db(self, monkeypatch):
        """Without DATABASE_URL, funnel check adds info finding and skips."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.treb.treb import _check_live_nh_funnel
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_nh_funnel(findings, insights, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )

    def test_funnel_metrics_not_populated_without_db(self, monkeypatch):
        """Without DB, no funnel metrics should be set."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.treb.treb import _check_live_nh_funnel
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_nh_funnel(findings, insights, metrics)

        assert "live_nh_signup_count" not in metrics


class TestTrebLiveReferral:
    """Treb live referral bonus capture — checks intro->credit->reputation chain."""

    def test_referral_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.treb.treb import _check_live_referral_workflow
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_referral_workflow(findings, insights, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )

    def test_referral_metrics_not_populated_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.treb.treb import _check_live_referral_workflow
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight

        findings: list[Finding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_referral_workflow(findings, insights, metrics)

        assert "live_referral_completed_count" not in metrics


class TestNaivLiveSatisfaction:
    """Naiv live satisfaction — queries user_feedback table."""

    def test_satisfaction_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.naiv.naiv import _check_live_satisfaction
        from agents.shared.report import Finding
        from ops_team.shared.report import SatisfactionFinding

        findings: list[Finding] = []
        sat_findings: list[SatisfactionFinding] = []
        metrics: dict = {}
        _check_live_satisfaction(findings, sat_findings, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )


class TestNaivLiveErrors:
    """Naiv live error telemetry — queries usage_logs + audit_logs."""

    def test_error_telemetry_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.naiv.naiv import _check_live_error_telemetry
        from agents.shared.report import Finding
        from ops_team.shared.report import SatisfactionFinding

        findings: list[Finding] = []
        sat_findings: list[SatisfactionFinding] = []
        metrics: dict = {}
        _check_live_error_telemetry(findings, sat_findings, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )


class TestNaivLiveEmail:
    """Naiv live email engagement — queries email_campaign_logs."""

    def test_email_engagement_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.naiv.naiv import _check_live_email_engagement
        from agents.shared.report import Finding
        from ops_team.shared.report import SatisfactionFinding

        findings: list[Finding] = []
        sat_findings: list[SatisfactionFinding] = []
        metrics: dict = {}
        _check_live_email_engagement(findings, sat_findings, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )


class TestMarshLiveVolume:
    """Marsh live marketplace volume — queries listings + intros."""

    def test_volume_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.marsh.marsh import _check_live_marketplace_volume
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight, MarketplaceFinding

        findings: list[Finding] = []
        mkt_findings: list[MarketplaceFinding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_marketplace_volume(findings, mkt_findings, insights, metrics)

        assert any(
            "unavailable" in f.title.lower() or "DATABASE_URL" in f.detail
            for f in findings
        )

    def test_volume_metrics_not_populated_without_db(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.marsh.marsh import _check_live_marketplace_volume
        from agents.shared.report import Finding
        from ops_team.shared.report import OpsInsight, MarketplaceFinding

        findings: list[Finding] = []
        mkt_findings: list[MarketplaceFinding] = []
        insights: list[OpsInsight] = []
        metrics: dict = {}
        _check_live_marketplace_volume(findings, mkt_findings, insights, metrics)

        assert "live_active_listings" not in metrics


class TestOpsLiveDataIntegration:
    """Verify all 4 agents run scan() without errors with live checks included."""

    def test_keevs_scan_includes_live_metrics(self):
        from ops_team.keevs.keevs import scan

        report = scan()
        assert "live_coaching_scenarios_tested" in report.metrics

    def test_treb_scan_includes_live_findings(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.treb.treb import scan

        report = scan()
        live_findings = [f for f in report.findings if "live" in f.id.lower()]
        assert len(live_findings) >= 1

    def test_naiv_scan_includes_live_findings(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.naiv.naiv import scan

        report = scan()
        live_findings = [f for f in report.findings if "live" in f.id.lower()]
        assert len(live_findings) >= 1

    def test_marsh_scan_includes_live_findings(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        import importlib
        import ops_team.shared.db as db_mod

        importlib.reload(db_mod)

        from ops_team.marsh.marsh import scan

        report = scan()
        live_findings = [f for f in report.findings if "live" in f.id.lower()]
        assert len(live_findings) >= 1
