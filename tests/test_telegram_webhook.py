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
