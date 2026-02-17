"""Tests for Keevs AI Job Coach endpoints and service logic."""

import uuid as uuid_mod
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.services.coach import (
    _assemble_context,
    _mock_briefing,
    _mock_chat_response,
    get_suggested_prompts,
)
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "keevs@test.com",
            "password": "Testpass123",
            "full_name": "Keevs Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "keevs@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_with_data(auth_headers: dict, client: AsyncClient) -> dict:
    """Create contacts, preferences, and an application."""
    # Contacts
    contacts_data = [
        {"first_name": "Alice", "last_name": "Eng", "company": "Google", "position": "SWE"},
        {"first_name": "Bob", "last_name": "PM", "company": "Stripe", "position": "PM"},
        {"first_name": "Carol", "last_name": "DS", "company": "Stripe", "position": "Data Scientist"},
    ]
    await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth_headers,
        json={"contacts": contacts_data},
    )
    # Preferences
    await client.put(
        "/api/v1/preferences/job",
        headers=auth_headers,
        json={
            "target_role": "Software Engineer",
            "target_seniority": "Senior",
            "target_locations": ["Singapore"],
        },
    )
    # Application
    await client.post(
        "/api/v1/applications",
        headers=auth_headers,
        json={"company_name": "Stripe", "role_title": "SWE", "status": "message_sent"},
    )
    return auth_headers


# ---------------------------------------------------------------------------
# TestCoachBriefingEndpoint
# ---------------------------------------------------------------------------


class TestCoachBriefingEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/coach/briefing")
        assert resp.status_code in (401, 403)

    async def test_returns_briefing(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["briefing"], str)
        assert len(data["briefing"]) > 0

    async def test_response_envelope(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        data = body["data"]
        assert "briefing" in data
        assert "context_snapshot" in data
        assert "suggested_prompts" in data
        assert "generated_at" in data

    async def test_context_snapshot_keys(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        ctx = resp.json()["data"]["context_snapshot"]
        assert "user" in ctx
        assert "preferences" in ctx
        assert "network" in ctx
        assert "pipeline" in ctx
        assert "credits" in ctx
        assert "market" in ctx
        assert "recent_searches" in ctx

    async def test_briefing_cached(self, client: AsyncClient, auth_headers: dict):
        """Second call uses cache — _assemble_context called only once."""
        with patch(
            "app.services.coach._assemble_context",
            new_callable=AsyncMock,
            return_value={
                "user": {"name": "Cache Test", "title": None, "company": None, "location": None},
                "preferences": None,
                "network": None,
                "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
                "recent_searches": [],
                "credits": 0,
                "market": None,
            },
        ) as mock_ctx:
            resp1 = await client.get("/api/v1/coach/briefing", headers=auth_headers)
            assert resp1.status_code == 200

            resp2 = await client.get("/api/v1/coach/briefing", headers=auth_headers)
            assert resp2.status_code == 200

            assert mock_ctx.call_count == 1

    async def test_briefing_with_data(
        self, client: AsyncClient, user_with_data: dict
    ):
        resp = await client.get("/api/v1/coach/briefing", headers=user_with_data)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["briefing"]) > 20
        # Should reference the user's name
        assert "Keevs" in data["briefing"]

    async def test_suggested_prompts_returned(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get("/api/v1/coach/briefing", headers=auth_headers)
        prompts = resp.json()["data"]["suggested_prompts"]
        assert isinstance(prompts, list)
        assert len(prompts) >= 1


# ---------------------------------------------------------------------------
# TestCoachChatEndpoint
# ---------------------------------------------------------------------------


class TestCoachChatEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/coach/chat",
            json={"message": "hello"},
        )
        assert resp.status_code in (401, 403)

    async def test_returns_response(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={"message": "What should I focus on today?"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["response"], str)
        assert len(data["response"]) > 0

    async def test_chat_uses_context(self, client: AsyncClient, auth_headers: dict):
        """Passing context_snapshot still returns a valid response."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={
                "message": "Tell me about my network",
                "context_snapshot": {
                    "user": {"name": "Test", "title": None, "company": None, "location": None},
                    "preferences": None,
                    "network": {
                        "total_contacts": 42,
                        "top_companies": [{"company": "Google", "count": 10}],
                        "summary": "42 contacts",
                    },
                    "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
                    "recent_searches": [],
                    "credits": 100,
                    "market": None,
                },
            },
        )
        assert resp.status_code == 200
        response_text = resp.json()["data"]["response"]
        # Mock should reference network data
        assert "42" in response_text or "network" in response_text.lower()

    async def test_chat_with_history(self, client: AsyncClient, auth_headers: dict):
        """Conversation history is accepted."""
        resp = await client.post(
            "/api/v1/coach/chat",
            headers=auth_headers,
            json={
                "message": "Thanks, what else?",
                "conversation_history": [
                    {"role": "keevs", "content": "Here's your briefing."},
                    {"role": "user", "content": "Tell me about credits"},
                    {"role": "keevs", "content": "You have 50 credits."},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["response"]


# ---------------------------------------------------------------------------
# TestContextAssembly
# ---------------------------------------------------------------------------


class TestContextAssembly:
    async def test_context_shape(self, client: AsyncClient, auth_headers: dict):
        """Verify all keys are present in assembled context."""
        me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        user_id = uuid_mod.UUID(me_resp.json()["data"]["id"])

        async with TestSessionLocal() as db:
            ctx = await _assemble_context(user_id, db)

        assert "user" in ctx
        assert "preferences" in ctx
        assert "network" in ctx
        assert "pipeline" in ctx
        assert "recent_searches" in ctx
        assert "credits" in ctx
        assert "market" in ctx
        assert ctx["user"]["name"] == "Keevs Tester"

    async def test_context_with_applications(
        self, client: AsyncClient, user_with_data: dict
    ):
        """Context includes pipeline data from applications."""
        me_resp = await client.get("/api/v1/auth/me", headers=user_with_data)
        user_id = uuid_mod.UUID(me_resp.json()["data"]["id"])

        async with TestSessionLocal() as db:
            ctx = await _assemble_context(user_id, db)

        assert ctx["pipeline"]["total"] >= 1
        assert len(ctx["pipeline"]["status_counts"]) >= 1


# ---------------------------------------------------------------------------
# TestMockResponses
# ---------------------------------------------------------------------------


class TestMockResponses:
    def test_mock_briefing_includes_name(self):
        context = {
            "user": {"name": "Alice Smith", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(context)
        assert "Alice" in briefing

    def test_mock_briefing_with_follow_ups(self):
        context = {
            "user": {"name": "Bob", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": None,
            "pipeline": {"status_counts": {"message_sent": 2}, "follow_ups_needed": 2, "total": 2},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        briefing = _mock_briefing(context)
        assert "2" in briefing
        assert "follow-up" in briefing.lower()

    def test_mock_chat_response_network(self):
        context = {
            "user": {"name": "Test", "title": None, "company": None, "location": None},
            "preferences": None,
            "network": {
                "total_contacts": 50,
                "top_companies": [{"company": "Google", "count": 10}],
            },
            "pipeline": {"status_counts": {}, "follow_ups_needed": 0, "total": 0},
            "recent_searches": [],
            "credits": 0,
            "market": None,
        }
        response = _mock_chat_response("Tell me about my network", context)
        assert "50" in response
        assert "Google" in response
