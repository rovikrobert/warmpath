"""Tests for POST /api/v1/feedback endpoint."""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "feedback@test.com",
            "password": "Testpass123",
            "full_name": "Feedback Tester",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "feedback@test.com", "password": "Testpass123"},
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_submit_feedback(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "search_results", "rating": 1, "comment": "Great matches!"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["feature"] == "search_results"
    assert data["rating"] == 1
    assert "id" in data


@pytest.mark.asyncio
async def test_submit_feedback_thumbs_down(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "intro_draft", "rating": -1},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["rating"] == -1


@pytest.mark.asyncio
async def test_submit_feedback_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "search_results", "rating": 1},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_submit_feedback_validates_rating(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "search_results", "rating": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_validates_featu[RESEND_KEY_REDACTED](client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "", "rating": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 422
