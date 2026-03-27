"""Tests for the Telegram webhook endpoint."""

from __futu[RESEND_KEY_REDACTED] import annotations

import pytest
from httpx import AsyncClient


class TestTelegramWebhook:
    """Tests for POST /api/v1/telegram/webhook."""

    @pytest.mark.asyncio
    async def test_valid_status_command(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "from": {"id": 99, "first_name": "Rovik"},
                "chat": {"id": 99},
                "text": "status",
            },
        }
        response = await client.post(
            "/api/v1/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret-token"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ok"] is True
        assert data["command"] == "status"

    @pytest.mark.asyncio
    async def test_missing_secret_header(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {"update_id": 1, "message": {"text": "status", "chat": {"id": 1}}}
        response = await client.post("/api/v1/telegram/webhook", json=payload)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_wrong_secret(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {"update_id": 1, "message": {"text": "status", "chat": {"id": 1}}}
        response = await client.post(
            "/api/v1/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-token"},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_no_message_in_payload(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {"update_id": 1}
        response = await client.post(
            "/api/v1/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret-token"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["ok"] is True

    @pytest.mark.asyncio
    async def test_approve_command(self, client: AsyncClient, monkeypatch):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {
            "update_id": 2,
            "message": {
                "message_id": 2,
                "from": {"id": 99, "first_name": "Rovik"},
                "chat": {"id": 99},
                "text": "1=yes",
            },
        }
        response = await client.post(
            "/api/v1/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret-token"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ok"] is True
        assert data["command"] == "approve_item"

    @pytest.mark.asyncio
    async def test_stats_command_parses_and_dispatches(
        self, client: AsyncClient, monkeypatch
    ):
        monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "test-secret-token")
        payload = {
            "update_id": 3,
            "message": {
                "message_id": 3,
                "from": {"id": 99, "first_name": "Rovik"},
                "chat": {"id": 99},
                "text": "stats",
            },
        }
        response = await client.post(
            "/api/v1/telegram/webhook",
            json=payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret-token"},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["ok"] is True
        assert data["command"] == "stats"


class TestGetPlatformStats:
    """Tests for the _get_platform_stats helper."""

    _STAT_KEYS = [
        "total_users",
        "users_with_uploads",
        "total_contacts",
        "marketplace_listings",
        "active_subscribers",
        "intro_requests",
        "signups_7d",
    ]

    @classmethod
    def _make_mock_engine(cls, values: list[int]):
        """Build a mock sync engine returning a single row with all stats."""
        from unittest.mock import MagicMock

        row_dict = dict(zip(cls._STAT_KEYS, values, strict=True))
        mock_conn = MagicMock()
        mock_conn.execute.return_value.mappings.return_value.one.return_value = row_dict
        mock_conn.__enter__ = lambda self: self
        mock_conn.__exit__ = MagicMock(return_value=False)

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_conn
        return mock_engine

    def test_returns_formatted_stats_string(self, monkeypatch):
        from app.api.telegram import _get_platform_stats

        # Order: total_users, users_with_uploads, total_contacts,
        #        marketplace_listings, active_subscribers, intro_requests, signups_7d
        mock_engine = self._make_mock_engine([22, 9, 150, 45, 0, 3, 7])
        monkeypatch.setattr("app.database._get_sync_engine", lambda: mock_engine)

        result = _get_platform_stats()

        assert "Total users: 22" in result
        assert "Uploaded CSV: 9 (41%)" in result
        assert "Active subscribers: 0" in result
        assert "Contacts: 150" in result
        assert "Marketplace listings: 45" in result
        assert "Intro requests: 3" in result
        assert "Signups (7d): 7" in result

    def test_zero_users_no_division_error(self, monkeypatch):
        from app.api.telegram import _get_platform_stats

        mock_engine = self._make_mock_engine([0, 0, 0, 0, 0, 0, 0])
        monkeypatch.setattr("app.database._get_sync_engine", lambda: mock_engine)

        result = _get_platform_stats()

        assert "Total users: 0" in result
        assert "(0%)" in result

    def test_null_scalars_treated_as_zero(self, monkeypatch):
        from app.api.telegram import _get_platform_stats

        mock_engine = self._make_mock_engine([None, None, None, None, None, None, None])
        monkeypatch.setattr("app.database._get_sync_engine", lambda: mock_engine)

        result = _get_platform_stats()

        assert "Total users: 0" in result
        assert "(0%)" in result

    def test_db_error_propagates_to_caller(self, monkeypatch):
        """_get_platform_stats raises on DB failure; _handle_command catches it."""
        from unittest.mock import MagicMock

        from app.api.telegram import _get_platform_stats

        mock_engine = MagicMock()
        mock_engine.connect.side_effect = ConnectionError("DB down")
        monkeypatch.setattr("app.database._get_sync_engine", lambda: mock_engine)

        with pytest.raises(ConnectionError, match="DB down"):
            _get_platform_stats()


class TestStatsFounderGating:
    """Verify stats command is founder-only."""

    def test_non_founder_gets_rejection(self):
        from unittest.mock import patch

        from app.api.telegram import _handle_command

        with patch("app.api.telegram._send_telegram_reply") as mock_reply:
            _handle_command(
                "stats", {"command": "stats"}, chat_id=999, is_founder=False
            )

        mock_reply.assert_called_once_with(999, "Stats is founder-only.")

    def test_founder_gets_stats(self, monkeypatch):
        from unittest.mock import patch

        from app.api.telegram import _handle_command

        monkeypatch.setattr(
            "app.api.telegram._get_platform_stats",
            lambda: "Platform Stats\n==============\nTotal users: 5",
        )

        with patch("app.api.telegram._send_telegram_reply") as mock_reply:
            _handle_command("stats", {"command": "stats"}, chat_id=123, is_founder=True)

        mock_reply.assert_called_once_with(
            123, "Platform Stats\n==============\nTotal users: 5"
        )
