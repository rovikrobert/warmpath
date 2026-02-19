"""Tests for user capabilities computation and intent endpoints."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User
from app.services.capabilities import compute_user_capabilities

from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="caps@test.com", full_name="Test User"
        )
    return headers


class TestComputeCapabilities:
    """Unit tests for compute_user_capabilities."""

    @pytest.mark.asyncio
    async def test_empty_user(self):
        """User with no activity has all flags False."""
        import uuid

        async with TestSessionLocal() as session:
            fake_id = uuid.uuid4()
            caps = await compute_user_capabilities(fake_id, session)
            assert caps.has_contacts is False
            assert caps.has_searches is False
            assert caps.has_listings is False
            assert caps.has_subscription is False
            assert caps.facilitation_count == 0

    @pytest.mark.asyncio
    async def test_with_contacts(self):
        """User who uploaded contacts has has_contacts=True."""
        from app.models.contact import Contact

        async with TestSessionLocal() as session:
            user = User(
                email="caps-contacts@example.com",
                full_name="Caps Test",
            )
            session.add(user)
            await session.flush()

            contact = Contact(
                user_id=user.id,
                first_name="Jane",
                last_name="Doe",
                full_name="Jane Doe",
                source="csv",
            )
            session.add(contact)
            await session.flush()

            caps = await compute_user_capabilities(user.id, session)
            assert caps.has_contacts is True
            assert caps.has_searches is False

    @pytest.mark.asyncio
    async def test_subscription(self):
        """User with paid plan has has_subscription=True."""
        async with TestSessionLocal() as session:
            user = User(
                email="caps-sub@example.com",
                full_name="Sub Test",
                plan_tier="pro",
            )
            session.add(user)
            await session.flush()

            caps = await compute_user_capabilities(user.id, session)
            assert caps.has_subscription is True


class TestMeEndpointCapabilities:
    """GET /auth/me should include capabilities."""

    @pytest.mark.asyncio
    async def test_me_includes_capabilities(
        self, client: AsyncClient, auth_headers: dict
    ):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "capabilities" in data
        caps = data["capabilities"]
        assert "has_contacts" in caps
        assert "has_searches" in caps
        assert "has_listings" in caps
        assert "has_subscription" in caps
        assert "facilitation_count" in caps
        # New user has no activity
        assert caps["has_contacts"] is False
        assert caps["facilitation_count"] == 0

    @pytest.mark.asyncio
    async def test_me_includes_intent(self, client: AsyncClient, auth_headers: dict):
        """GET /auth/me returns intent field (initially None)."""
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "intent" in data


class TestPatchIntent:
    """PATCH /auth/intent endpoint tests."""

    @pytest.mark.asyncio
    async def test_set_intent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.patch(
            "/api/v1/auth/intent",
            headers=auth_headers,
            json={"intent": "find_referrals"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["intent"] == "find_referrals"

    @pytest.mark.asyncio
    async def test_invalid_intent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.patch(
            "/api/v1/auth/intent",
            headers=auth_headers,
            json={"intent": "invalid_value"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_all_valid_values(self, client: AsyncClient, auth_headers: dict):
        for intent_val in ("find_referrals", "sha[RESEND_KEY_REDACTED]", "explore"):
            resp = await client.patch(
                "/api/v1/auth/intent",
                headers=auth_headers,
                json={"intent": intent_val},
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["intent"] == intent_val
