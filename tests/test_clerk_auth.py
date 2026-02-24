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


async def test_jit_provision_creates_user_when_webhook_missing(
    client: AsyncClient,
    monkeypatch,
):
    """JIT provisioning creates DB user from Clerk API when webhook hasn't arrived."""
    import httpx

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    # Mock Clerk API response
    clerk_api_response = {
        "id": clerk_id,
        "email_addresses": [
            {
                "email_address": "jit@test.com",
                "verification": {"status": "verified"},
            }
        ],
        "first_name": "JIT",
        "last_name": "User",
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return clerk_api_response

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr("app.config.settings.CLERK_SECRET_KEY", "sk_test_fake")

    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "jit@test.com"
    assert resp.json()["data"]["full_name"] == "JIT User"


async def test_jit_provision_falls_back_to_401_when_clerk_api_fails(
    client: AsyncClient,
    monkeypatch,
):
    """JIT provisioning returns 401 when Clerk API is unreachable."""
    import httpx

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr("app.config.settings.CLERK_SECRET_KEY", "sk_test_fake")

    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_jit_provision_skipped_when_no_clerk_secret(client: AsyncClient):
    """JIT provisioning is skipped when CLERK_SECRET_KEY is empty (test default)."""
    token = create_test_clerk_token("user_no_secret_xyz")
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Default CLERK_SECRET_KEY is empty, so JIT is skipped, falls through to 401
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_jit_provision_blocked_for_deleted_user(
    client: AsyncClient,
    monkeypatch,
):
    """JIT provisioning is blocked when user's email is on suppression list."""
    import hashlib
    from datetime import datetime, timezone

    import httpx

    from app.models.privacy import SuppressionList

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"
    email = "deleted-user@test.com"

    # Add email to suppression list (simulating prior account deletion)
    email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    async with TestSessionLocal() as db:
        db.add(
            SuppressionList(
                email_hash=email_hash,
                reason="account_deleted",
                requested_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    # Mock Clerk API to return user data with the deleted email
    clerk_api_response = {
        "id": clerk_id,
        "email_addresses": [
            {
                "email_address": email,
                "verification": {"status": "verified"},
            }
        ],
        "first_name": "Deleted",
        "last_name": "User",
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return clerk_api_response

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr("app.config.settings.CLERK_SECRET_KEY", "sk_test_fake")

    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Should return 401 — JIT provisioning is blocked for deleted users
    assert resp.status_code == 401
    assert "not found" in resp.json()["detail"].lower()


async def test_jit_provision_handles_race_condition(
    client: AsyncClient,
    monkeypatch,
):
    """JIT provisioning handles IntegrityError (webhook arrived first) gracefully."""
    import httpx

    clerk_id = f"user_{uuid.uuid4().hex[:12]}"

    # Pre-create the user (simulating webhook arriving first)
    async with TestSessionLocal() as db:
        user = User(
            email="race@test.com",
            full_name="Race User",
            clerk_user_id=clerk_id,
        )
        db.add(user)
        await db.commit()

    # Mock Clerk API to return the same user (JIT will try to create, hit IntegrityError)
    clerk_api_response = {
        "id": clerk_id,
        "email_addresses": [
            {
                "email_address": "race@test.com",
                "verification": {"status": "verified"},
            }
        ],
        "first_name": "Race",
        "last_name": "User",
    }

    class MockResponse:
        status_code = 200

        def json(self):
            return clerk_api_response

    class MockClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            return MockResponse()

    monkeypatch.setattr(httpx, "AsyncClient", MockClient)
    monkeypatch.setattr("app.config.settings.CLERK_SECRET_KEY", "sk_test_fake")

    token = create_test_clerk_token(clerk_id)
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Should succeed — either JIT finds existing user or normal lookup works
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == "race@test.com"
