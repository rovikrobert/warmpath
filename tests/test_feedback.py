"""Tests for POST /api/v1/feedback endpoint."""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, create_test_user_in_db


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="feedback@test.com", full_name="Feedback Tester"
        )
    return headers


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
async def test_submit_feedback_validates_rating(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "search_results", "rating": 5},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_feedback_validates_feature_length(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/feedback",
        json={"feature": "", "rating": 1},
        headers=auth_headers,
    )
    assert resp.status_code == 422
