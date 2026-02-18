"""Tests for finance team agent upgrades (CoS audit gap resolution)."""

from __future__ import annotations


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
