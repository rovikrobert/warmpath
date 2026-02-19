"""Auth endpoint tests — Clerk JWT integration."""

from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.conftest import (
    TestSessionLocal,
    create_test_user_in_db,
    create_test_clerk_token,
)


async def test_me_returns_profile_and_capabilities(client: AsyncClient):
    """GET /me returns user profile with capabilities for valid Clerk JWT."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="me@test.com", full_name="Me User"
        )
    resp = await client.get("/api/v1/auth/me", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["email"] == "me@test.com"
    assert body["data"]["full_name"] == "Me User"
    assert body["data"]["plan_tier"] == "free"
    assert "id" in body["data"]
    assert "capabilities" in body["data"]
    assert "meta" in body

    # No sensitive fields exposed
    data_str = str(body["data"]).lower()
    assert "password" not in data_str
    assert "clerk_user_id" not in body["data"]


async def test_me_without_token_returns_401(client: AsyncClient):
    """GET /me without Authorization header returns 401/403."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


async def test_me_with_invalid_token_returns_401(client: AsyncClient):
    """GET /me with garbage token returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


async def test_me_with_unknown_clerk_id_returns_401(client: AsyncClient):
    """GET /me with valid JWT but unknown clerk_user_id returns 401."""
    token = create_test_clerk_token("user_nonexistent_abc")
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_intent_update(client: AsyncClient):
    """PATCH /intent updates user onboarding intent."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="intent@test.com", full_name="Intent User"
        )
    resp = await client.patch(
        "/api/v1/auth/intent",
        json={"intent": "find_referrals"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["intent"] == "find_referrals"


async def test_delete_account_requires_confirmation(client: AsyncClient):
    """DELETE account without confirm_deletion returns 422."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="nodelete@test.com", full_name="No Delete"
        )
    resp = await client.post(
        "/api/v1/auth/delete-account",
        json={"confirm_deletion": False},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_delete_account_success(client: AsyncClient):
    """DELETE account with confirmation deletes the user."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="delete@test.com", full_name="Delete Me"
        )
        user_id = user.id

    resp = await client.post(
        "/api/v1/auth/delete-account",
        json={"confirm_deletion": True},
        headers=headers,
    )
    assert resp.status_code == 200
    assert "deleted" in resp.json()["data"]["message"].lower()

    # Verify user is gone
    async with TestSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        assert result.scalar_one_or_none() is None
