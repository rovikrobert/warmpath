"""Tests for finance team agent upgrades (CoS audit gap resolution)."""

from __future__ import annotations
import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestFinanceQueryExecutor:
    def test_get_executor_returns_instance(self):
        from finance_team.shared.query_executor import get_finance_executor

        qe = get_finance_executor()
        assert qe is not None

    def test_get_executor_singleton(self):
        from finance_team.shared.query_executor import get_finance_executor

        qe1 = get_finance_executor()
        qe2 = get_finance_executor()
        assert qe1 is qe2

    def test_graceful_degradation_without_db(self):
        from finance_team.shared.query_executor import get_finance_executor

        qe = get_finance_executor()
        result = qe.query_template("credit_balances", {"start_date": "2024-01-01"})
        assert result == []

    def test_available_templates_listed(self):
        from finance_team.shared.sql_templates import FINANCE_TEMPLATES

        assert "credit_balances" in FINANCE_TEMPLATES
        assert "credit_velocity" in FINANCE_TEMPLATES
        assert "credit_distribution" in FINANCE_TEMPLATES
        assert "monthly_revenue" in FINANCE_TEMPLATES
        assert "dsar_pending" in FINANCE_TEMPLATES
        assert "deletion_verification" in FINANCE_TEMPLATES


class TestFinanceSQLTemplates:
    def test_all_templates_registered(self):
        from finance_team.shared.sql_templates import FINANCE_TEMPLATES

        expected = [
            "credit_balances",
            "credit_velocity",
            "credit_distribution",
            "credit_expiry_rate",
            "earn_spend_by_type",
            "zero_balance_users",
            "dsar_pending",
            "deletion_verification",
            "monthly_revenue",
        ]
        for name in expected:
            assert name in FINANCE_TEMPLATES, f"Missing template: {name}"

    def test_templates_are_nonempty_sql(self):
        from finance_team.shared.sql_templates import FINANCE_TEMPLATES

        for name, sql in FINANCE_TEMPLATES.items():
            assert isinstance(sql, str), f"{name} is not a string"
            assert len(sql.strip()) > 10, f"{name} is too short"
            assert "select" in sql.lower() or "with" in sql.lower(), (
                f"{name} doesn't look like SQL"
            )

    def test_no_pii_columns_in_select(self):
        from finance_team.shared.sql_templates import FINANCE_TEMPLATES

        pii_columns = {
            "first_name",
            "last_name",
            "full_name",
            "email",
            "linkedin_url",
            "current_title",
            "current_company",
            "location",
            "notes",
            "how_you_know",
        }
        for name, sql in FINANCE_TEMPLATES.items():
            sql_lower = sql.lower()
            from_idx = sql_lower.find("from")
            if from_idx > 0:
                select_part = sql_lower[:from_idx]
                for col in pii_columns:
                    assert col not in select_part, (
                        f"Template '{name}' selects PII column '{col}'"
                    )

    def test_aggregation_templates_have_k_anonymity(self):
        import re

        from finance_team.shared.sql_templates import FINANCE_TEMPLATES

        for name, sql in FINANCE_TEMPLATES.items():
            sql_lower = sql.lower()
            if "group by" in sql_lower:
                has_having = bool(
                    re.search(r"having\s+count\s*\([^)]*\)\s*>=\s*(\d+)", sql_lower)
                )
                has_subquery = "from (" in sql_lower or "from\n(" in sql_lower
                assert has_having or has_subquery, (
                    f"Template '{name}' has GROUP BY without k-anonymity guard"
                )


class TestStripeClient:
    """Read-only Stripe API client for finance agents."""

    def test_get_client_returns_instance(self):
        from finance_team.shared.stripe_client import get_stripe_client

        client = get_stripe_client()
        assert client is not None

    def test_graceful_degradation_without_key(self, monkeypatch):
        """Without STRIPE_SECRET_KEY, all methods return None."""
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        # Reset singleton
        import finance_team.shared.stripe_client as mod

        mod._client = None

        client = mod.get_stripe_client()
        assert client.is_available() is False
        assert client.get_balance() is None
        assert client.list_charges() is None
        assert client.list_subscriptions() is None
        assert client.list_disputes() is None

    def test_available_when_key_set(self, monkeypatch):
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_fake_key_for_testing")
        import finance_team.shared.stripe_client as mod

        mod._client = None

        client = mod.get_stripe_client()
        assert client.is_available() is True

    def test_api_methods_exist(self):
        from finance_team.shared.stripe_client import StripeClient

        client = StripeClient()
        assert callable(getattr(client, "get_balance", None))
        assert callable(getattr(client, "list_charges", None))
        assert callable(getattr(client, "list_subscriptions", None))
        assert callable(getattr(client, "list_disputes", None))
        assert callable(getattr(client, "get_customer", None))


class TestStripeCustomerIdColumn:
    """User model should have stripe_customer_id for webhook→user mapping."""

    def test_user_model_has_stripe_customer_id(self):
        from app.models.user import User

        assert hasattr(User, "stripe_customer_id")

    def test_stripe_customer_id_nullable(self):
        from app.models.user import User

        col = User.__table__.columns["stripe_customer_id"]
        assert col.nullable is True


class TestWebhookHandlers:
    """Webhook handlers must call credit/subscription services, not just log."""

    def test_checkout_completed_is_async(self):
        from app.api.webhooks import _handle_checkout_completed

        assert inspect.iscoroutinefunction(_handle_checkout_completed)

    def test_subscription_deleted_is_async(self):
        from app.api.webhooks import _handle_subscription_deleted

        assert inspect.iscoroutinefunction(_handle_subscription_deleted)

    def test_all_handlers_are_async(self):
        from app.api.webhooks import _EVENT_HANDLERS

        for event_type, handler in _EVENT_HANDLERS.items():
            assert inspect.iscoroutinefunction(handler), (
                f"Handler for {event_type} is not async"
            )

    def test_event_handlers_registered(self):
        from app.api.webhooks import _EVENT_HANDLERS

        expected = [
            "checkout.session.completed",
            "invoice.paid",
            "invoice.payment_failed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ]
        for event in expected:
            assert event in _EVENT_HANDLERS, f"Missing handler for {event}"

    def test_resolve_user_exists(self):
        from app.api.webhooks import _resolve_user

        assert inspect.iscoroutinefunction(_resolve_user)


class TestGDPRDeletionVerification:
    """Legal compliance agent can verify deletions via DB query."""

    def test_deletion_verification_check_exists(self):
        from finance_team.legal_compliance import legal_compliance

        assert hasattr(legal_compliance, "_check_deletion_verification")

    def test_deletion_verification_produces_finding_when_unavailable(self):
        """When DB is unavailable, produce an info finding (not a failure)."""
        from finance_team.legal_compliance.legal_compliance import (
            _check_deletion_verification,
        )

        findings = []
        compliance_findings = []
        metrics = {}

        _check_deletion_verification(findings, compliance_findings, metrics)

        assert metrics.get("deletion_verification_available") is False


class TestCreditVelocityAnalysis:
    """Credits manager should analyze credit velocity, distribution, expiry."""

    def test_gini_coefficient_perfect_equality(self):
        from finance_team.credits_manager.credits_manager import _compute_gini

        assert _compute_gini([10, 10, 10, 10]) == pytest.approx(0.0, abs=0.01)

    def test_gini_coefficient_perfect_inequality(self):
        from finance_team.credits_manager.credits_manager import _compute_gini

        assert _compute_gini([0, 0, 0, 100]) == pytest.approx(0.75, abs=0.01)

    def test_gini_coefficient_empty(self):
        from finance_team.credits_manager.credits_manager import _compute_gini

        assert _compute_gini([]) == 0.0

    def test_velocity_check_exists(self):
        from finance_team.credits_manager import credits_manager

        assert hasattr(credits_manager, "_check_credit_velocity_live")

    def test_distribution_check_exists(self):
        from finance_team.credits_manager import credits_manager

        assert hasattr(credits_manager, "_check_credit_distribution_live")

    def test_expiry_check_exists(self):
        from finance_team.credits_manager import credits_manager

        assert hasattr(credits_manager, "_check_expiry_rate_live")

    def test_zero_balance_check_exists(self):
        from finance_team.credits_manager import credits_manager

        assert hasattr(credits_manager, "_check_zero_balance_rate_live")

    def test_velocity_degrades_without_db(self):
        from finance_team.credits_manager.credits_manager import (
            _check_credit_velocity_live,
        )

        # Mock the executor to simulate no DB (singleton may be contaminated
        # by other tests in the same xdist worker process)
        mock_qe = MagicMock()
        mock_qe.is_available.return_value = False
        with patch(
            "finance_team.shared.query_executor.get_finance_executor",
            return_value=mock_qe,
        ):
            findings = []
            fin_findings = []
            metrics = {}
            _check_credit_velocity_live(findings, fin_findings, metrics)
            assert metrics.get("credit_velocity_available") is False


class TestCashRunwayForecasting:
    """Finance manager should forecast cash runway."""

    def test_monthly_fixed_costs_defined(self):
        from finance_team.shared.config import MONTHLY_FIXED_COSTS

        assert isinstance(MONTHLY_FIXED_COSTS, dict)
        assert "infrastructure" in MONTHLY_FIXED_COSTS
        assert sum(MONTHLY_FIXED_COSTS.values()) > 0

    def test_cash_runway_check_exists(self):
        from finance_team.finance_manager import finance_manager

        assert hasattr(finance_manager, "_check_cash_runway")

    def test_cash_runway_without_data(self):
        """Without Stripe or DB, uses fixed costs only."""
        from finance_team.finance_manager.finance_manager import _check_cash_runway

        findings = []
        fin_findings = []
        metrics = {}
        cost_snapshots = []
        _check_cash_runway(findings, fin_findings, metrics, cost_snapshots)

        assert "monthly_burn_rate" in metrics
        assert metrics["monthly_burn_rate"] > 0


class TestInvestorReportExport:
    """Investor report export as Excel workbook."""

    def test_generate_workbook_returns_bytes(self):
        from finance_team.shared.report_export import generate_workbook

        wb_bytes = generate_workbook()
        assert isinstance(wb_bytes, bytes)
        assert wb_bytes[:2] == b"PK"

    def test_workbook_has_expected_sheets(self):
        from finance_team.shared.report_export import generate_workbook
        from io import BytesIO

        import openpyxl

        wb_bytes = generate_workbook()
        wb = openpyxl.load_workbook(BytesIO(wb_bytes))
        sheet_names = wb.sheetnames

        assert "Summary" in sheet_names
        assert "Financial Health" in sheet_names
        assert "Compliance" in sheet_names
        assert "Technical Readiness" in sheet_names

    def test_investor_relations_has_generate_method(self):
        from finance_team.investor_relations import investor_relations

        assert hasattr(investor_relations, "_generate_investor_report")
