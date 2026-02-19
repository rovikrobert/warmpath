"""Tests for the benchmarks API — CRUD, summary, admin enforcement, edge cases."""

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
            db, email="benchadmin@test.com", full_name="Bench Admin", is_admin=True
        )
    return headers


@pytest_asyncio.fixture
async def user_headers(client: AsyncClient) -> dict:
    """Create a non-admin user and return auth headers."""
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="benchuser@test.com", full_name="Bench User"
        )
    return headers


def _benchmark_body(**overrides) -> dict:
    base = {
        "company_name": "JobBoard Pro",
        "product_category": "job_board",
        "pricing_model": "subscription",
        "domain": "jobboardpro.com",
        "lowest_paid_price": 29.99,
        "free_tier_exists": True,
        "enterprise_available": False,
        "notes": "Standard job board pricing",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Auth enforcement
# ---------------------------------------------------------------------------


class TestBenchmarkAuth:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/benchmarks")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_non_admin_returns_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/benchmarks", headers=user_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_create_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.post(
            "/api/v1/benchmarks",
            headers=user_headers,
            json=_benchmark_body(),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_summary_403(self, client: AsyncClient, user_headers: dict):
        resp = await client.get("/api/v1/benchmarks/summary", headers=user_headers)
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestBenchmarkCRUD:
    @pytest.mark.asyncio
    async def test_create_benchmark(self, client: AsyncClient, admin_headers: dict):
        resp = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["company_name"] == "JobBoard Pro"
        assert data["product_category"] == "job_board"
        assert data["pricing_model"] == "subscription"
        assert data["lowest_paid_price"] == 29.99

    @pytest.mark.asyncio
    async def test_get_benchmark(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(company_name="GetBench"),
        )
        bid = create.json()["data"]["id"]

        resp = await client.get(f"/api/v1/benchmarks/{bid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["company_name"] == "GetBench"

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.get(f"/api/v1/benchmarks/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_invalid_uuid_returns_404(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.get("/api/v1/benchmarks/not-a-uuid", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_benchmark(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(company_name="UpdateBench"),
        )
        bid = create.json()["data"]["id"]

        resp = await client.put(
            f"/api/v1/benchmarks/{bid}",
            headers=admin_headers,
            json={"company_name": "Updated Bench", "lowest_paid_price": 19.99},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["company_name"] == "Updated Bench"
        assert resp.json()["data"]["lowest_paid_price"] == 19.99

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.put(
            f"/api/v1/benchmarks/{fake}",
            headers=admin_headers,
            json={"company_name": "Nope"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_benchmark(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(company_name="DeleteBench"),
        )
        bid = create.json()["data"]["id"]

        resp = await client.delete(f"/api/v1/benchmarks/{bid}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Verify soft-deleted
        get_resp = await client.get(f"/api/v1/benchmarks/{bid}", headers=admin_headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient, admin_headers: dict):
        fake = str(uuid.uuid4())
        resp = await client.delete(f"/api/v1/benchmarks/{fake}", headers=admin_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_invalid_product_category(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(product_category="invalid"),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_invalid_pricing_model(
        self, client: AsyncClient, admin_headers: dict
    ):
        resp = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(pricing_model="invalid"),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# List + pagination + filters
# ---------------------------------------------------------------------------


class TestBenchmarkList:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/benchmarks", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["meta"]["total"] == 0
        assert resp.json()["meta"]["total_pages"] == 1

    @pytest.mark.asyncio
    async def test_list_filter_product_category(
        self, client: AsyncClient, admin_headers: dict
    ):
        await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(company_name="JB1", product_category="job_board"),
        )
        await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(
                company_name="RP1", product_category="referral_platform"
            ),
        )

        resp = await client.get(
            "/api/v1/benchmarks?product_category=referral_platform",
            headers=admin_headers,
        )
        assert resp.json()["meta"]["total"] == 1
        assert resp.json()["data"][0]["company_name"] == "RP1"

    @pytest.mark.asyncio
    async def test_list_pagination(self, client: AsyncClient, admin_headers: dict):
        for i in range(5):
            await client.post(
                "/api/v1/benchmarks",
                headers=admin_headers,
                json=_benchmark_body(company_name=f"Page{i}"),
            )

        resp = await client.get(
            "/api/v1/benchmarks?page=1&per_page=2", headers=admin_headers
        )
        assert resp.json()["meta"]["total"] == 5
        assert resp.json()["meta"]["total_pages"] == 3
        assert len(resp.json()["data"]) == 2

        resp2 = await client.get(
            "/api/v1/benchmarks?page=3&per_page=2", headers=admin_headers
        )
        assert len(resp2.json()["data"]) == 1

    @pytest.mark.asyncio
    async def test_deleted_not_in_list(self, client: AsyncClient, admin_headers: dict):
        create = await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(company_name="WillDelete"),
        )
        bid = create.json()["data"]["id"]
        await client.delete(f"/api/v1/benchmarks/{bid}", headers=admin_headers)

        resp = await client.get("/api/v1/benchmarks", headers=admin_headers)
        names = [b["company_name"] for b in resp.json()["data"]]
        assert "WillDelete" not in names


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


class TestBenchmarkSummary:
    @pytest.mark.asyncio
    async def test_summary_empty(self, client: AsyncClient, admin_headers: dict):
        resp = await client.get("/api/v1/benchmarks/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_benchmarks"] == 0
        assert data["avg_lowest_paid_price"] is None
        assert data["warmpath_percentile"] is None

    @pytest.mark.asyncio
    async def test_summary_with_data(self, client: AsyncClient, admin_headers: dict):
        # Create benchmarks with different prices
        await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(
                company_name="Cheap",
                lowest_paid_price=10.00,
                pricing_model="freemium",
            ),
        )
        await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(
                company_name="Mid",
                lowest_paid_price=30.00,
                pricing_model="subscription",
            ),
        )
        await client.post(
            "/api/v1/benchmarks",
            headers=admin_headers,
            json=_benchmark_body(
                company_name="Expensive",
                lowest_paid_price=50.00,
                pricing_model="subscription",
            ),
        )

        resp = await client.get("/api/v1/benchmarks/summary", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_benchmarks"] == 3
        assert data["avg_lowest_paid_price"] is not None
        # avg = (10 + 30 + 50) / 3 = 30.0
        assert abs(data["avg_lowest_paid_price"] - 30.0) < 0.01
        assert data["model_distribution"]["subscription"] == 2
        assert data["model_distribution"]["freemium"] == 1
        # warmpath_percentile: products above $25 = 2 (30, 50) out of 3
        assert data["warmpath_percentile"] is not None
        assert abs(data["warmpath_percentile"] - 66.7) < 0.1
