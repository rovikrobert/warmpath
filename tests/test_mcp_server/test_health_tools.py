"""Tests for MCP health tools."""

from __futu[RESEND_KEY_REDACTED] import annotations

from unittest.mock import MagicMock, patch

from mcp_server.tools.health import check_health, check_services, redis_info


class TestCheckHealth:
    @patch("mcp_server.tools.health._check_health_impl")
    def test_returns_health_status(self, mock_check: MagicMock) -> None:
        mock_check.return_value = MagicMock(
            healthy=True, status_code=200, response_ms=42.5
        )
        result = check_health()
        assert result["healthy"] is True
        assert result["response_ms"] == 42.5

    @patch("mcp_server.tools.health._check_health_impl")
    def test_unhealthy_returns_false(self, mock_check: MagicMock) -> None:
        mock_check.return_value = MagicMock(healthy=False, status_code=0, response_ms=0)
        result = check_health()
        assert result["healthy"] is False


class TestCheckServices:
    @patch("mcp_server.tools.health._check_alembic")
    @patch("mcp_server.tools.health._check_redis")
    @patch("mcp_server.tools.health._check_celery")
    @patch("mcp_server.tools.health._check_db")
    def test_aggregates_all_services(
        self, mock_db, mock_celery, mock_redis, mock_alembic
    ) -> None:
        mock_db.return_value = {"status": "ok"}
        mock_celery.return_value = {"status": "ok", "workers": 1}
        mock_redis.return_value = {"status": "ok"}
        mock_alembic.return_value = {"status": "ok", "head": "abc123"}

        result = check_services()
        assert "database" in result
        assert "redis" in result
        assert "celery" in result
        assert "alembic" in result


class TestRedisInfo:
    @patch("mcp_server.tools.health._get_redis_client")
    def test_returns_redis_stats(self, mock_get: MagicMock) -> None:
        client = MagicMock()
        client.ping.return_value = True
        client.info.return_value = {
            "used_memory_human": "1.5M",
            "connected_clients": 3,
            "db0": "keys=42,expires=10",
        }
        client.llen.return_value = 0
        mock_get.return_value = client

        result = redis_info()
        assert result["connected"] is True
        assert "memory" in result

    @patch("mcp_server.tools.health._get_redis_client")
    def test_redis_unavailable(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        result = redis_info()
        assert "error" in result
