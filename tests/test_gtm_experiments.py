"""Tests for the experiments API — CRUD, start, complete, admin enforcement, edge cases."""

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
            db, email="expadmin@test.com", full_name="Exp Admin", is_admin=True
        )
    return headers


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict:
    """Create a non-admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="expuser@test.com", full_name="Exp User"
        )
    return headers


def _experiment_body(**overrides) -> dict:
    base = {
        "name": "Pricing Test A",
        "experiment_type": "pricing",
        "hypothesis": "Lower price increases signups",
        "variants": {"control": "$30/mo", "variant_a": "$20/mo"},
        "metrics": {"signup_rate": "primary"},
        "target_sample_size": 500,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestExperimentAuth:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/experiments")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/experiments", headers=user_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_create_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.post(
            "/api/v1/experiments",
            headers=user_headers,
            json=_experiment_body(),
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestExperimentCRUD:
    @pytest.mark.asyncio
    async def test_create_experiment(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Pricing Test A"
        assert data["experiment_type"] == "pricing"
        assert data["status"] == "draft"
        assert data["created_by"] is not None

    @pytest.mark.asyncio
    async def test_get_experiment(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="GetExp"),
        )
        eid = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/experiments/{eid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "GetExp"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/experiments/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_404(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get("/api/v1/experiments/not-a-uuid", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_experiment(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="UpdateExp"),
        )
        eid = create.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/experiments/{eid}",
            headers=admin_headers,
            json={"name": "Updated Exp", "target_sample_size": 1000},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["name"] == "Updated Exp"
        assert resp.json()["data"]["target_sample_size"] == 1000

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.put(
            f"/api/v1/experiments/{fake}",
            headers=admin_headers,
            json={"name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_experiment(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="DeleteExp"),
        )
        eid = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/experiments/{eid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify soft-deleted
        get_resp = await client.get(f"/api/v1/experiments/{eid}", headers=admin_headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/experiments/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invalid_experiment_type(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(experiment_type="invalid"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_status(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(status="invalid"),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List + pagination + filters
# ---------------------------------------------------------------------------


class TestExperimentList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/experiments", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["meta"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_filter_status(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="Draft1"),
        )
        # Create and start one
        create2 = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="Running1"),
        )
        eid = create2.json()["data"]["id"]
        await client.post(f"/api/v1/experiments/{eid}/start", headers=admin_headers)

        resp = await client.get(
            "/api/v1/experiments?status=running", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["name"] == "Running1"

    @pytest.mark.asyncio
    async def test_list_filter_type(self, client: AsyncClient, admin_headers: dict):
        await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="PricingExp", experiment_type="pricing"),
        )
        await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="MsgExp", experiment_type="messaging"),
        )

        resp = await client.get(
            "/api/v1/experiments?experiment_type=messaging", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["name"] == "MsgExp"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient, admin_headers: dict):
        for i in range(5):
            await client.post(
                "/api/v1/experiments",
                headers=admin_headers,
                json=_experiment_body(name=f"Page{i}"),
            )

        resp = await client.get(
            "/api/v1/experiments?page=1&per_page=2", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 5
        assert resp.json()["meta"]["total_pages"] == 3
        assert len(resp.json()["data"]) == 2

    @pytest.mark.asyncio
    async def test_deleted_not_in_list(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="WillDelete"),
        )
        eid = create.json()["data"]["id"]
        await client.delete(f"/api/v1/experiments/{eid}", headers=admin_headers)

        resp = await client.get("/api/v1/experiments", headers=admin_headers)
        names = [e["name"] for e in resp.json()["data"]]
        assert "WillDelete" not in names


# ---------------------------------------------------------------------------
# Start / Complete
# ---------------------------------------------------------------------------


class TestExperimentStart:
    @pytest.mark.asyncio
    async def test_start_experiment(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="StartMe"),
        )
        eid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/experiments/{eid}/start", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "running"
        assert resp.json()["data"]["started_at"] is not None

    @pytest.mark.asyncio
    async def test_start_non_draft_fails(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="AlreadyRunning"),
        )
        eid = create.json()["data"]["id"]

        # Start once
        first_start = await client.post(
            f"/api/v1/experiments/{eid}/start", headers=admin_headers
        )
        assert first_start.status_code == 200

        # Try to start again — should fail
        resp = await client.post(
            f"/api/v1/experiments/{eid}/start", headers=admin_headers
        )
        assert resp.status_code == 422
        assert "error" in resp.json()

    @pytest.mark.asyncio
    async def test_start_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/experiments/{fake}/start", headers=admin_headers
        )
        assert resp.status_code == 404


class TestExperimentComplete:
    @pytest.mark.asyncio
    async def test_complete_running_experiment(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="CompleteMe"),
        )
        eid = create.json()["data"]["id"]
        await client.post(f"/api/v1/experiments/{eid}/start", headers=admin_headers)

        resp = await client.post(
            f"/api/v1/experiments/{eid}/complete",
            headers=admin_headers,
            json={
                "results": {"signup_rate": 0.15},
                "conclusion": "Lower price wins",
                "recommendation": "Ship $20/mo",
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert data["ended_at"] is not None
        assert data["results"] == {"signup_rate": 0.15}
        assert data["conclusion"] == "Lower price wins"
        assert data["recommendation"] == "Ship $20/mo"

    @pytest.mark.asyncio
    async def test_complete_draft_fails(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="DraftComplete"),
        )
        eid = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/v1/experiments/{eid}/complete",
            headers=admin_headers,
            json={"conclusion": "Nope"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_complete_without_body(
        self, client: AsyncClient, admin_headers: dict
    ):
        create = await client.post(
            "/api/v1/experiments",
            headers=admin_headers,
            json=_experiment_body(name="NoBody"),
        )
        eid = create.json()["data"]["id"]
        await client.post(f"/api/v1/experiments/{eid}/start", headers=admin_headers)

        # Send empty JSON body — all fields are optional
        resp = await client.post(
            f"/api/v1/experiments/{eid}/complete",
            headers=admin_headers,
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_complete_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/experiments/{fake}/complete",
            headers=admin_headers,
            json={"conclusion": "N/A"},
        )
        assert resp.status_code == 404
