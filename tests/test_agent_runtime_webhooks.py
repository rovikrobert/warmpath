"""Tests for GitHub webhook → agent event ingestion."""

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture(autouse=True)
def _set_webhook_secret(monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.GITHUB_AGENT_WEBHOOK_SECRET", "test-secret"
    )
    monkeypatch.setattr("app.config.settings.AGENT_RUNTIME_ENABLED", True)


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
    from unittest.mock import AsyncMock, patch

    body = json.dumps(github_push_payload).encode()
    secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    with patch("app.api.agent_webhooks.stream_add", AsyncMock(return_value=None)):
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
    assert resp.json()["data"]["status"] == "accepted"


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


@pytest.mark.asyncio
async def test_github_webhook_dispatches_event_to_redis_stream(github_push_payload):
    """Valid webhook dispatches serialized event to warmpath:agent_events stream."""
    from unittest.mock import AsyncMock, patch

    body = json.dumps(github_push_payload).encode()
    secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    mock_stream_add = AsyncMock(return_value="1-0")

    with patch("app.api.agent_webhooks.stream_add", mock_stream_add):
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
    mock_stream_add.assert_called_once()
    call_args = mock_stream_add.call_args
    assert call_args[0][0] == "warmpath:agent_events"
    dispatched = json.loads(call_args[0][1]["event"])
    assert dispatched["type"] == "code_change"
    assert dispatched["source"] == "github"


@pytest.mark.asyncio
async def test_github_webhook_returns_503_when_runtime_disabled(github_push_payload):
    """Webhook returns 503 when AGENT_RUNTIME_ENABLED is False."""
    from unittest.mock import patch

    body = json.dumps(github_push_payload).encode()
    secret = "test-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

    with patch("app.config.settings.AGENT_RUNTIME_ENABLED", False):
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
    assert resp.status_code == 503
    assert "disabled" in resp.json()["detail"].lower()
