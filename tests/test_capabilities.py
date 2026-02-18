"""Tests for user capabilities computation and intent endpoints."""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User
from app.services.capabilities import compute_user_capabilities

# Re-use test DB session from conftest
from tests.conftest import TestSessionLocal


async def _signup(client: AsyncClient, email: str) -> str:
    """Quick signup, return access token (no verification needed for these tests)."""
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": email,
            "password": "Str0ngP@ss!",
            "full_name": "Test User",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]["access_token"]


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
                password_hash="fakehash",
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
                password_hash="fakehash",
                plan_tier="pro",
            )
            session.add(user)
            await session.flush()

            caps = await compute_user_capabilities(user.id, session)
            assert caps.has_subscription is True


class TestMeEndpointCapabilities:
    """GET /auth/me should include capabilities."""

    @pytest.mark.asyncio
    async def test_me_includes_capabilities(self, client: AsyncClient):
        token = await _signup(client, "me-caps@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
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
    async def test_me_includes_intent(self, client: AsyncClient):
        """GET /auth/me returns intent field (initially None)."""
        token = await _signup(client, "me-intent@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "intent" in data


class TestPatchIntent:
    """PATCH /auth/intent endpoint tests."""

    @pytest.mark.asyncio
    async def test_set_intent(self, client: AsyncClient):
        token = await _signup(client, "intent-set@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.patch(
            "/api/v1/auth/intent",
            headers=headers,
            json={"intent": "find_referrals"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["intent"] == "find_referrals"

    @pytest.mark.asyncio
    async def test_invalid_intent(self, client: AsyncClient):
        token = await _signup(client, "intent-invalid@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.patch(
            "/api/v1/auth/intent",
            headers=headers,
            json={"intent": "invalid_value"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_all_valid_values(self, client: AsyncClient):
        token = await _signup(client, "intent-all@example.com")
        headers = {"Authorization": f"Bearer {token}"}

        for intent_val in ("find_referrals", "share_network", "explore"):
            resp = await client.patch(
                "/api/v1/auth/intent",
                headers=headers,
                json={"intent": intent_val},
            )
            assert resp.status_code == 200
            assert resp.json()["data"]["intent"] == intent_val
