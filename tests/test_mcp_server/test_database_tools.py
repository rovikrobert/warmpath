"""Tests for MCP database tools."""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import MagicMock, patch

from mcp_server.tools.database import (
    get_schema,
    list_templates,
    query_sql,
    query_template,
)


class TestListTemplates:
    def test_returns_all_template_names(self) -> None:
        result = list_templates()
        assert "daily_signups" in [e["name"] for e in result]
        assert "credit_balances" in [e["name"] for e in result]
        assert len(result) >= 20

    def test_each_entry_has_name_and_source(self) -> None:
        result = list_templates()
        for entry in result:
            assert "name" in entry
            assert "source" in entry


class TestQueryTemplate:
    def test_unknown_template_returns_error(self) -> None:
        result = query_template(name="nonexistent")
        assert "error" in result

    @patch("mcp_server.tools.database._get_data_executor")
    def test_known_template_delegates_to_executor(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = True
        executor.execute_template.return_value = [{"count": 5}]
        mock_get.return_value = executor

        result = query_template(
            name="daily_signups",
            params={"start_date": "2024-01-01", "end_date": "2024-02-01"},
        )
        assert result["rows"] == [{"count": 5}]

    @patch("mcp_server.tools.database._get_data_executor")
    def test_db_unavailable_returns_error(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = False
        mock_get.return_value = executor

        result = query_template(name="daily_signups")
        assert "error" in result


class TestQuerySql:
    @patch("mcp_server.tools.database._get_data_executor")
    def test_executes_privacy_validated_sql(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = True
        executor.execute_sql.return_value = [{"total": 42}]
        mock_get.return_value = executor

        result = query_sql(sql="SELECT COUNT(*) AS total FROM users")
        assert result["rows"] == [{"total": 42}]

    @patch("mcp_server.tools.database._get_data_executor")
    def test_privacy_violation_returns_error(self, mock_get: MagicMock) -> None:
        from data_team.shared.privacy_guard import PrivacyViolation

        executor = MagicMock()
        executor.is_available.return_value = True
        executor.execute_sql.side_effect = PrivacyViolation("PII in SELECT")
        mock_get.return_value = executor

        result = query_sql(sql="SELECT email FROM contacts")
        assert "error" in result


class TestGetSchema:
    @patch("mcp_server.tools.database._get_engine")
    def test_returns_table_list(self, mock_engine: MagicMock) -> None:
        with patch("mcp_server.tools.database.sa_inspect") as mock_inspect:
            inspector = MagicMock()
            inspector.get_table_names.return_value = ["users", "contacts"]
            inspector.get_columns.return_value = [
                {"name": "id", "type": "UUID"},
                {"name": "created_at", "type": "TIMESTAMP"},
            ]
            mock_inspect.return_value = inspector
            mock_engine.return_value = MagicMock()

            result = get_schema()
            assert len(result["tables"]) == 2
            assert result["tables"][0]["name"] == "users"

    @patch("mcp_server.tools.database._get_engine")
    def test_no_engine_returns_error(self, mock_engine: MagicMock) -> None:
        mock_engine.return_value = None
        result = get_schema()
        assert "error" in result
