"""Tests for the partnerships API — CRUD, pipeline, advance, lose, metrics, admin enforcement."""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin_headers(client: AsyncClient) -> dict:
    """Create an admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="partadmin@test.com", full_name="Part Admin", is_admin=True
        )
    return headers


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict:
    """Create a non-admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="partuser@test.com", full_name="Part User"
        )
    return headers


def _partnership_body(**overrides) -> dict:
    base = {
        "partner_name": "CodeCamp SG",
        "partner_type": "bootcamp",
        "partner_domain": "codecamp.sg",
        "stage": "identified",
        "contact_name": "Jane Doe",
        "estimated_users": 500,
        "estimated_monthly_revenue": 2500.00,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestPartnershipAuth:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/partnerships")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/partnerships", headers=user_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_create_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.post(
            "/api/v1/partnerships",
            headers=user_headers,
            json=_partnership_body(),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_metrics_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/partnerships/metrics", headers=user_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestPartnershipCRUD:
    @pytest.mark.asyncio
    async def test_create_partnership(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["partner_name"] == "CodeCamp SG"
        assert data["partner_type"] == "bootcamp"
        assert data["stage"] == "identified"
        assert data["created_by"] is not None

    @pytest.mark.asyncio
    async def test_get_partnership(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="GetPartner"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/partnerships/{pid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["partner_name"] == "GetPartner"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/partnerships/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_404(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get(
            "/api/v1/partnerships/not-a-uuid", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_partnership(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="UpdatePartner"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/partnerships/{pid}",
            headers=admin_headers,
            json={"partner_name": "Updated Partner", "estimated_users": 1000},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["partner_name"] == "Updated Partner"
        assert resp.json()["data"]["estimated_users"] == 1000

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.put(
            f"/api/v1/partnerships/{fake}",
            headers=admin_headers,
            json={"partner_name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_partnership(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="DeletePartner"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/partnerships/{pid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify soft-deleted
        get_resp = await client.get(
            f"/api/v1/partnerships/{pid}", headers=admin_headers
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.delete(
            f"/api/v1/partnerships/{fake}", headers=admin_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invalid_partner_type(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_type="invalid_type"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_stage(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="invalid_stage"),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List + pagination + filters
# ---------------------------------------------------------------------------


class TestPartnershipList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/partnerships", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["meta"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_filter_stage(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="P1", stage="identified"),
        )
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="P2", stage="outreach"),
        )

        resp = await client.get(
            "/api/v1/partnerships?stage=outreach", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["partner_name"] == "P2"

    @pytest.mark.asyncio
    async def test_list_filter_partner_type(
        self, client: AsyncClient, admin_headers: dict
    ):
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="Boot1", partner_type="bootcamp"),
        )
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="Uni1", partner_type="university"),
        )

        resp = await client.get(
            "/api/v1/partnerships?partner_type=university", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["partner_name"] == "Uni1"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient, admin_headers: dict):
        for i in range(5):
            await client.post(
                "/api/v1/partnerships",
                headers=admin_headers,
                json=_partnership_body(partner_name=f"Page{i}"),
            )

        resp = await client.get(
            "/api/v1/partnerships?page=1&per_page=2", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 5
        assert resp.json()["meta"]["total_pages"] == 3
        assert len(resp.json()["data"]) == 2

    @pytest.mark.asyncio
    async def test_deleted_not_in_list(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="WillDelete"),
        )
        pid = create.json()["data"]["id"]
        await client.delete(f"/api/v1/partnerships/{pid}", headers=admin_headers)

        resp = await client.get("/api/v1/partnerships", headers=admin_headers)
        names = [p["partner_name"] for p in resp.json()["data"]]
        assert "WillDelete" not in names


# ---------------------------------------------------------------------------
# Advance / Lose
# ---------------------------------------------------------------------------


class TestPartnershipAdvance:
    @pytest.mark.asyncio
    async def test_advance_stage(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="identified"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/partnerships/{pid}/advance", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["stage"] == "outreach"

    @pytest.mark.asyncio
    async def test_advance_multiple_stages(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="identified"),
        )
        pid = create.json()["data"]["id"]

        expected = ["outreach", "conversation", "proposal", "negotiation", "signed"]
        for stage in expected:
            resp = await client.post(
                f"/api/v1/partnerships/{pid}/advance", headers=admin_headers
            )
            assert resp.json()["data"]["stage"] == stage

    @pytest.mark.asyncio
    async def test_advance_terminal_stage_fails(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="signed"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/partnerships/{pid}/advance", headers=admin_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_advance_lost_stage_fails(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="lost"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/partnerships/{pid}/advance", headers=admin_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_advance_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/partnerships/{fake}/advance", headers=admin_headers
        )
        assert resp.status_code == 404


class TestPartnershipLose:
    @pytest.mark.asyncio
    async def test_lose_partnership(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(stage="conversation"),
        )
        pid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/partnerships/{pid}/lose",
            headers=admin_headers,
            json={"reason": "Budget constraints"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["stage"] == "lost"
        assert resp.json()["data"]["lost_reason"] == "Budget constraints"

    @pytest.mark.asyncio
    async def test_lose_requires_reason(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(),
        )
        pid = create.json()["data"]["id"]

        # Missing reason should fail validation
        resp = await client.post(
            f"/api/v1/partnerships/{pid}/lose",
            headers=admin_headers,
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_lose_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/partnerships/{fake}/lose",
            headers=admin_headers,
            json={"reason": "Gone"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


class TestPartnershipMetrics:
    @pytest.mark.asyncio
    async def test_metrics_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/partnerships/metrics", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_active"] == 0
        assert data["conversion_rate"] is None

    @pytest.mark.asyncio
    async def test_metrics_with_data(self, client: AsyncClient, admin_headers: dict):
        # Create some partnerships in various stages
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(
                partner_name="Active1", stage="outreach", estimated_monthly_revenue=1000
            ),
        )
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="Signed1", stage="signed"),
        )
        await client.post(
            "/api/v1/partnerships",
            headers=admin_headers,
            json=_partnership_body(partner_name="Lost1", stage="lost"),
        )

        resp = await client.get("/api/v1/partnerships/metrics", headers=admin_headers)
        data = resp.json()["data"]
        assert data["total_active"] == 1
        assert data["deals_per_stage"]["outreach"] == 1
        assert data["deals_per_stage"]["signed"] == 1
        assert data["deals_per_stage"]["lost"] == 1
        # conversion_rate = signed / (signed + lost) = 1/2 = 0.5
        assert data["conversion_rate"] == 0.5
