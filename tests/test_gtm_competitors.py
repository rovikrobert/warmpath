"""Tests for the competitors API — CRUD, matrix, admin enforcement, edge cases."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """Create an admin user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "compadmin@test.com",
            "password": "Test1234!@#$",
            "full_name": "Comp Admin",
        },
    )
    async with TestSessionLocal() as s:
        from sqlalchemy import update

        await s.execute(
            update(User).where(User.email == "compadmin@test.com").values(is_admin=True)
        )
        await s.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "compadmin@test.com", "password": "Test1234!@#$"},
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict:
    """Create a non-admin user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "compuser@test.com",
            "password": "Test1234!@#$",
            "full_name": "Comp User",
        },
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "compuser@test.com", "password": "Test1234!@#$"},
    )
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _competitor_body(**overrides) -> dict:
    base = {
        "name": "RivalCo",
        "category": "direct",
        "domain": "rivalco.com",
        "threat_level": "high",
        "features": {"referral_matching": True, "csv_upload": True},
        "target_market": "tech professionals",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestCompetitorAuth:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/competitors")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/competitors", headers=user_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_create_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.post(
            "/api/v1/competitors",
            headers=user_headers,
            json=_competitor_body(),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_matrix_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/competitors/matrix", headers=user_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCompetitorCRUD:
    @pytest.mark.asyncio
    async def test_create_competitor(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "RivalCo"
        assert data["category"] == "direct"
        assert data["threat_level"] == "high"
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_get_competitor(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="GetMe"),
        )
        cid = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/competitors/{cid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "GetMe"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/competitors/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_404(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get("/api/v1/competitors/not-a-uuid", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_competitor(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="UpdateMe"),
        )
        cid = create.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/competitors/{cid}",
            headers=admin_headers,
            json={"name": "Updated", "threat_level": "critical"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated"
        assert resp.json()["data"]["threat_level"] == "critical"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.put(
            f"/api/v1/competitors/{fake}",
            headers=admin_headers,
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_competitor(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="DeleteMe"),
        )
        cid = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/competitors/{cid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify soft-deleted — not returned
        get_resp = await client.get(f"/api/v1/competitors/{cid}", headers=admin_headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/competitors/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invalid_category(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(category="nonexistent"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_threat_level(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(threat_level="extreme"),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List + pagination + filters
# ---------------------------------------------------------------------------


class TestCompetitorList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/competitors", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["meta"]["total"] == 0
        assert resp.json()["meta"]["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_list_returns_items(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="A Corp"),
        )
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="B Corp", category="indirect"),
        )

        resp = await client.get("/api/v1/competitors", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["meta"]["total"] == 2

    @pytest.mark.asyncio
    async def test_list_filter_category(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="Direct1"),
        )
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="Indirect1", category="indirect"),
        )

        resp = await client.get(
            "/api/v1/competitors?category=direct", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["name"] == "Direct1"

    @pytest.mark.asyncio
    async def test_list_filter_threat_level(
        self, client: AsyncClient, admin_headers: dict
    ):
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="HighThreat", threat_level="high"),
        )
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="LowThreat", threat_level="low"),
        )

        resp = await client.get(
            "/api/v1/competitors?threat_level=low", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["name"] == "LowThreat"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient, admin_headers: dict):
        for i in range(5):
            await client.post(
                "/api/v1/competitors",
                headers=admin_headers,
                json=_competitor_body(name=f"Page{i}"),
            )

        resp = await client.get(
            "/api/v1/competitors?page=1&per_page=2", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 5
        assert resp.json()["meta"]["total_pages"] == 3
        assert len(resp.json()["data"]) == 2

        resp2 = await client.get(
            "/api/v1/competitors?page=3&per_page=2", headers=admin_headers
        )
        assert len(resp2.json()["data"]) == 1

    @pytest.mark.asyncio
    async def test_deleted_not_in_list(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(name="WillDelete"),
        )
        cid = create.json()["data"]["id"]
        await client.delete(f"/api/v1/competitors/{cid}", headers=admin_headers)

        resp = await client.get("/api/v1/competitors", headers=admin_headers)
        names = [c["name"] for c in resp.json()["data"]]
        assert "WillDelete" not in names


# ---------------------------------------------------------------------------
# Feature matrix
# ---------------------------------------------------------------------------


class TestCompetitorMatrix:
    @pytest.mark.asyncio
    async def test_matrix_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/competitors/matrix", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["competitors"] == []
        assert data["all_features"] == []
        assert data["matrix"] == {}

    @pytest.mark.asyncio
    async def test_matrix_with_data(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(
                name="AlphaCo",
                features={"csv_upload": True, "ai_matching": True},
            ),
        )
        await client.post(
            "/api/v1/competitors",
            headers=admin_headers,
            json=_competitor_body(
                name="BetaCo",
                features={"csv_upload": True, "referral_bonus": True},
            ),
        )

        resp = await client.get("/api/v1/competitors/matrix", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["competitors"]) == 2
        assert "ai_matching" in data["all_features"]
        assert "csv_upload" in data["all_features"]
        assert "referral_bonus" in data["all_features"]
        assert data["matrix"]["AlphaCo"]["ai_matching"] is True
        assert data["matrix"]["AlphaCo"]["referral_bonus"] is False
        assert data["matrix"]["BetaCo"]["referral_bonus"] is True
