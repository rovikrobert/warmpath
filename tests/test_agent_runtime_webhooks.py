"""Tests for GitHub webhook → agent event ingestion."""

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _set_webhook_secret(monkeypatch):
    monkeypatch.setattr("app.api.agent_webhooks._GITHUB_WEBHOOK_SECRET", "test-secret")


@pytest.fixture
def github_push_payload():
    return {
        "ref": "refs/heads/fix/auth-bypass",
        "commits": [{"id": "abc123", "message": "fix: patch auth bypass"}],
        "repository": {"full_name": "rovikrobert/warmpath"},
        "pusher": {"name": "rovikrobert"},
    }


@pytest.mark.asyncio
async def test_github_webhook_returns_202_on_valid_push(github_push_payload):
    """Valid GitHub push webhook returns 202 accepted."""
    body = json.dumps(github_push_payload).encode()
    secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/agent-webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": sig,
                "X-GitHub-Event": "push",
            },
        )
    assert resp.status_code == 202
    assert resp.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_github_webhook_rejects_invalid_signature():
    """Invalid HMAC signature returns 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/agent-webhooks/github",
            content=b'{"ref":"refs/heads/main"}',
            headers={
                "Content-Type": "application/json",
                "X-Hub-Signature-256": "sha256=invalid",
                "X-GitHub-Event": "push",
            },
        )
    assert resp.status_code == 401
