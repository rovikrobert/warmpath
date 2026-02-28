"""Tests for MCP audit tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from mcp_server.tools.audit import (
    enrichment_stats,
    privacy_audit_log,
    query_audit_log,
)


class TestQueryAuditLog:
    @patch("mcp_server.tools.audit._get_data_executor")
    def test_returns_audit_entries(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = True
        executor.execute_sql.return_value = [{"action": "login", "count": 15}]
        mock_get.return_value = executor

        result = query_audit_log(action="login", limit=10)
        assert result["rows"] == [{"action": "login", "count": 15}]

    @patch("mcp_server.tools.audit._get_data_executor")
    def test_db_unavailable(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = False
        mock_get.return_value = executor

        result = query_audit_log()
        assert "error" in result


class TestEnrichmentStats:
    @patch("mcp_server.tools.audit._get_data_executor")
    def test_returns_stats(self, mock_get: MagicMock) -> None:
        executor = MagicMock()
        executor.is_available.return_value = True
        executor.execute_sql.return_value = [{"total": 100, "enriched": 60}]
        mock_get.return_value = executor

        result = enrichment_stats()
        assert "rows" in result


class TestPrivacyAuditLog:
    @patch("mcp_server.tools.audit._get_guard")
    def test_returns_log_entries(self, mock_get: MagicMock) -> None:
        guard = MagicMock()
        guard.get_audit_log.return_value = [
            {"timestamp": "2024-01-01T00:00:00Z", "agent": "test", "sql_hash": 123}
        ]
        mock_get.return_value = guard

        result = privacy_audit_log()
        assert len(result["entries"]) == 1

    @patch("mcp_server.tools.audit._get_guard")
    def test_empty_log(self, mock_get: MagicMock) -> None:
        guard = MagicMock()
        guard.get_audit_log.return_value = []
        mock_get.return_value = guard

        result = privacy_audit_log()
        assert result["entries"] == []
