from httpx import AsyncClient


async def test_signup_returns_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "new@example.com",
            "password": "Secret123",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["token_type"] == "bearer"
    assert len(body["data"]["access_token"]) > 0

    # Decode the JWT and verify expected claims
    from jose import jwt
    from app.config import settings

    payload = jwt.decode(
        body["data"]["access_token"], settings.SECRET_KEY, algorithms=["HS256"]
    )
    assert payload["type"] == "access"
    assert "sub" in payload  # user ID (UUID string)
    assert "ver" in payload  # token version
    assert "exp" in payload  # expiration timestamp
    assert payload["ver"] == 0  # Initial signup should have token_version=0

    # Ensure no sensitive data in response body
    assert "password" not in str(body["data"]).lower()
    assert "hashed" not in str(body["data"]).lower()


async def test_signup_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "Secret123",
        "full_name": "Dup User",
    }
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 409
    detail = resp.json().get("detail", "")
    assert (
        "email" in detail.lower()
        or "already" in detail.lower()
        or "exist" in detail.lower()
    )


async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "login@example.com",
            "password": "Secret123",
            "full_name": "Login User",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"

    # Decode the JWT and verify expected claims
    from jose import jwt
    from app.config import settings

    payload = jwt.decode(
        body["data"]["access_token"], settings.SECRET_KEY, algorithms=["HS256"]
    )
    assert payload["type"] == "access"
    assert "sub" in payload  # user ID
    assert "exp" in payload  # expiration
    assert "ver" in payload  # token version

    # Ensure no password or sensitive data in response
    assert "password" not in str(body).lower()
    assert "hashed" not in str(body).lower()


async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "wrong@example.com",
            "password": "Secret123",
            "full_name": "Wrong",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "badpassword"},
    )
    assert resp.status_code == 401
    # Error message should be generic to prevent email enumeration
    detail = resp.json().get("detail", "")
    assert "invalid" in detail.lower()
    # Must not reveal whether the email exists or the password is wrong specifically
    assert "password is wrong" not in detail.lower()
    assert "email exists" not in detail.lower()


async def test_login_nonexistent_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Secret123"},
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert detail == "Invalid email or password"
    # Verify the error is identical to wrong-password case (prevents email enumeration)
    # — same status code AND same generic message for both cases
    assert "nobody" not in detail  # Must not echo the email back
    assert "not found" not in detail.lower()  # Must not reveal non-existence


async def test_me_with_valid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "me@example.com",
            "password": "Secret123",
            "full_name": "Me User",
        },
    )
    token = resp.json()["data"]["access_token"]
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["email"] == "me@example.com"
    assert body["data"]["full_name"] == "Me User"
    assert body["data"]["plan_tier"] == "free"
    assert "id" in body["data"]
    assert "created_at" in body["data"]
    assert "meta" in body

    # Verify sensitive fields are NOT exposed in the /me response
    data_str = str(body["data"]).lower()
    assert "password" not in data_str  # No password hash
    assert "hashed" not in data_str
    assert "secret" not in data_str  # No JWT secret
    assert "token_version" not in body["data"]  # Internal field, not exposed


async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)
    # Verify no user data is leaked in the error response
    body = resp.json()
    assert "email" not in body.get("data", {}) if "data" in body else True
    assert "full_name" not in body.get("data", {}) if "data" in body else True


async def test_me_with_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert resp.status_code == 401
    detail = resp.json().get("detail", "")
    # Error should mention token issue without leaking internal details
    assert "token" in detail.lower() or "invalid" in detail.lower()
    assert "secret" not in detail.lower()  # Must not leak the JWT secret
