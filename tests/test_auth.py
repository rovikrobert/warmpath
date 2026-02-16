from httpx import AsyncClient


async def test_signup_returns_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "new@example.com",
            "password": "secret123",
            "full_name": "New User",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "data" in body
    assert "meta" in body
    assert body["data"]["token_type"] == "bearer"
    assert len(body["data"]["access_token"]) > 0


async def test_signup_duplicate_email(client: AsyncClient):
    payload = {
        "email": "dup@example.com",
        "password": "secret123",
        "full_name": "Dup User",
    }
    await client.post("/api/v1/auth/signup", json=payload)
    resp = await client.post("/api/v1/auth/signup", json=payload)
    assert resp.status_code == 409


async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "login@example.com",
            "password": "secret123",
            "full_name": "Login User",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "secret123"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["access_token"]
    assert body["data"]["token_type"] == "bearer"


async def test_login_wrong_password(client: AsyncClient):
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "wrong@example.com",
            "password": "secret123",
            "full_name": "Wrong",
        },
    )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "badpassword"},
    )
    assert resp.status_code == 401


async def test_login_nonexistent_email(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "secret123"},
    )
    assert resp.status_code == 401


async def test_me_with_valid_token(client: AsyncClient):
    resp = await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "me@example.com",
            "password": "secret123",
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


async def test_me_without_token(client: AsyncClient):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code in (401, 403)


async def test_me_with_invalid_token(client: AsyncClient):
    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer invalidtoken"},
    )
    assert resp.status_code == 401
