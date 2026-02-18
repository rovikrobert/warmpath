"""Tests for Partnerships scanner enhancements — pipeline infrastructure, supply-side activation.

Verifies:
- _check_pipeline_infrastructure detects GTM models, API, and service
- _check_supply_activation_data detects activation metric data sources
- Graceful handling when files don't exist
- New metrics/insights appear in scan() report
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import patch



class TestCheckPipelineInfrastructure:
    """Partnership pipeline infrastructure detection."""

    def test_detects_missing_infrastructure(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_pipeline_infrastructure

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_pipeline_infrastructure(findings, insights, metrics)

        assert metrics["pipeline_model_exists"] is False
        assert metrics["pipeline_api_exists"] is False
        assert metrics["pipeline_service_exists"] is False
        assert any(f.id == "PART-NO-PIPELINE-MODEL" for f in findings)
        assert any(i.id == "part-insight-pipeline" for i in insights)

    def test_detects_full_infrastructure(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_pipeline_infrastructure

        # Create files with expected content
        (tmp_path / "app" / "models").mkdir(parents=True)
        (tmp_path / "app" / "api").mkdir(parents=True)
        (tmp_path / "app" / "services").mkdir(parents=True)

        (tmp_path / "app" / "models" / "gtm.py").write_text(
            "class PartnershipOpportunity(Base): pass"
        )
        (tmp_path / "app" / "api" / "partnerships.py").write_text(
            "from fastapi import APIRouter"
        )
        (tmp_path / "app" / "services" / "gtm_service.py").write_text(
            "async def create_partnership(): pass"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_pipeline_infrastructure(findings, insights, metrics)

        assert metrics["pipeline_model_exists"] is True
        assert metrics["pipeline_api_exists"] is True
        assert metrics["pipeline_service_exists"] is True
        assert not any(f.id == "PART-NO-PIPELINE-MODEL" for f in findings)

        # Check insight reports "full"
        pipeline_insight = [i for i in insights if i.id == "part-insight-pipeline"]
        assert len(pipeline_insight) == 1
        assert "full" in pipeline_insight[0].title

    def test_partial_infrastructure(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_pipeline_infrastructure

        (tmp_path / "app" / "models").mkdir(parents=True)
        (tmp_path / "app" / "models" / "gtm.py").write_text(
            "class PartnershipOpportunity(Base): pass"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_pipeline_infrastructure(findings, insights, metrics)

        pipeline_insight = [i for i in insights if i.id == "part-insight-pipeline"]
        assert "partial" in pipeline_insight[0].title


class TestCheckSupplyActivationData:
    """Supply-side activation data source detection."""

    def test_detects_missing_data_sources(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_supply_activation_data

        (tmp_path / "app" / "models").mkdir(parents=True)

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_supply_activation_data(findings, insights, metrics)

        assert metrics["activation_data_coverage"] == 0.0
        assert any(f.id == "PART-ACTIVATION-DATA-GAPS" for f in findings)
        assert any(i.id == "part-insight-activation" for i in insights)

    def test_detects_present_data_sources(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_supply_activation_data

        (tmp_path / "app" / "models").mkdir(parents=True)
        (tmp_path / "app" / "models" / "marketplace.py").write_text(
            "class NetworkSharingPreferences(Base): pass\n"
            "class MarketplaceListing(Base): pass\n"
        )
        (tmp_path / "app" / "models" / "contact.py").write_text(
            "class CsvUpload(Base): pass"
        )
        (tmp_path / "app" / "models" / "enrichment.py").write_text(
            "class UsageLog(Base): pass"
        )

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_supply_activation_data(findings, insights, metrics)

        assert metrics["activation_data_coverage"] == 100.0
        assert not any(f.id == "PART-ACTIVATION-DATA-GAPS" for f in findings)

    def test_partial_data_sources(self, tmp_path):
        from agents.shared.report import Finding
        from gtm_team.shared.report import MarketInsight
        from gtm_team.partnerships.scanner import _check_supply_activation_data

        (tmp_path / "app" / "models").mkdir(parents=True)
        (tmp_path / "app" / "models" / "marketplace.py").write_text(
            "class MarketplaceListing(Base): pass"
        )
        (tmp_path / "app" / "models" / "contact.py").write_text(
            "class CsvUpload(Base): pass"
        )
        (tmp_path / "app" / "models" / "enrichment.py").write_text("# empty")

        findings: list[Finding] = []
        insights: list[MarketInsight] = []
        metrics: dict = {}

        with patch("gtm_team.partnerships.scanner.PROJECT_ROOT", tmp_path):
            _check_supply_activation_data(findings, insights, metrics)

        assert 0 < metrics["activation_data_coverage"] < 100


class TestPartnershipsScanIntegration:
    """Full scan() includes new pipeline and activation metrics."""

    def test_scan_includes_pipeline_metrics(self):
        from gtm_team.partnerships.scanner import scan

        report = scan()

        assert "pipeline_model_exists" in report.metrics
        assert "pipeline_api_exists" in report.metrics
        assert "pipeline_service_exists" in report.metrics

    def test_scan_includes_activation_metrics(self):
        from gtm_team.partnerships.scanner import scan

        report = scan()

        assert "activation_data_sources" in report.metrics
        assert "activation_data_coverage" in report.metrics
