import uuid

from httpx import AsyncClient

from app.models.user import User
from tests.conftest import TestSessionLocal, create_test_clerk_token


async def test_get_current_user_with_valid_clerk_jwt(client: AsyncClient):
    """Valid Clerk JWT with matching user returns 200 and correct email."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        user = User(
            email="clerk@test.com",
            full_name="Clerk User",
            clerk_user_id=clerk_id,
        )
        db.add(user)
        await db.commit()
    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "clerk@test.com"


async def test_get_current_user_rejects_expired_token(client: AsyncClient):
    """Expired Clerk JWT returns 401."""
    import jwt as pyjwt

    from tests.conftest import TEST_CLERK_DOMAIN, _test_rsa_private

    token = pyjwt.encode(
        {
            "sub": "user_expired",
            "iss": f"https://{TEST_CLERK_DOMAIN}",
            "exp": 1000000000,
            "nbf": 0,
        },
        _test_rsa_private,
        algorithm="RS256",
    )
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert (
        "invalid" in resp.json()["detail"].lower()
        or "expired" in resp.json()["detail"].lower()
    )


async def test_get_current_user_rejects_unknown_clerk_id(client: AsyncClient):
    """Valid JWT but no matching user in DB returns 401 with 'not found'."""
    token = create_test_clerk_token("user_nonexistent_xyz")
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_get_current_user_rejects_deactivated_user(client: AsyncClient):
    """Valid JWT for a deactivated user returns 403."""
    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    async with TestSessionLocal() as db:
        user = User(
            email="deactivated@test.com",
            full_name="Deactivated",
            clerk_user_id=clerk_id,
            is_active=False,
        )
        db.add(user)
        await db.commit()
    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    assert "deactivated" in resp.json()["detail"].lower()


async def test_get_current_user_rejects_garbage_token(client: AsyncClient):
    """Garbage Bearer token returns 401."""
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401
    assert (
        "invalid" in resp.json()["detail"].lower()
        or "expired" in resp.json()["detail"].lower()
    )
