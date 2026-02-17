"""Tests for job recommendations endpoint and supporting helpers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient

from app.models.enrichment import EnrichmentCache
from app.services.board_registry import (
    companies_for_locations,
    get_display_name,
    get_region,
)
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "rectest@test.com",
            "password": "Testpass123",
            "full_name": "Rec Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "rectest@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def prefs_set(auth_headers: dict, client: AsyncClient) -> None:
    """Set job preferences with target_role."""
    await client.put(
        "/api/v1/preferences/job",
        headers=auth_headers,
        json={
            "target_role": "Software Engineer",
            "target_seniority": "Senior",
            "target_locations": ["Singapore"],
        },
    )


# Mock data for job fetcher
MOCK_JOBS = [
    {
        "title": "Senior Software Engineer",
        "department": "Engineering",
        "location": "Singapore",
        "url": "https://example.com/jobs/1",
        "source": "greenhouse",
        "source_job_id": "rec-001",
        "posted_at": None,
        "is_remote": False,
        "raw_data": {},
        "role_relevance": 85,
    },
    {
        "title": "Staff Software Engineer",
        "department": "Engineering",
        "location": "Remote",
        "url": "https://example.com/jobs/2",
        "source": "greenhouse",
        "source_job_id": "rec-002",
        "posted_at": None,
        "is_remote": True,
        "raw_data": {},
        "role_relevance": 70,
    },
]


def _mock_fetch(name, boards):
    """Return mock jobs for any company."""
    return MOCK_JOBS


def _mock_match(jobs, role, sen=None):
    """Return all jobs as matched."""
    return jobs


# ---------------------------------------------------------------------------
# Test: Board Registry Helpers
# ---------------------------------------------------------------------------


class TestBoardRegistryHelpers:
    def test_display_name_known(self):
        assert get_display_name("sea-group") == "Sea Group"

    def test_display_name_fallback(self):
        assert get_display_name("unknown-company") == "Unknown Company"

    def test_display_name_simple(self):
        assert get_display_name("stripe") == "Stripe"

    def test_region_known(self):
        assert get_region("grab") == "Singapore / SEA"
        assert get_region("stripe") == "US / Global"

    def test_region_unknown(self):
        assert get_region("nonexistent") is None

    def test_companies_for_locations_sea(self):
        result = companies_for_locations(["Singapore"])
        # SEA companies should appear first
        sea_companies = {
            "grab",
            "sea-group",
            "shopee",
            "lazada",
            "gojek",
            "carousell",
            "foodpanda",
            "ninja-van",
            "patsnap",
            "endowus",
            "syfe",
            "aspire",
            "funding-societies",
            "carro",
        }
        first_batch = set(result[: len(sea_companies)])
        assert sea_companies == first_batch

    def test_companies_for_locations_all(self):
        """No locations returns all companies."""
        result = companies_for_locations(None)
        assert len(result) > 50  # We have ~70 companies

    def test_companies_for_locations_empty_list(self):
        result = companies_for_locations([])
        assert len(result) > 50

    def test_companies_for_locations_unrecognized(self):
        """Unrecognized location returns all companies."""
        result = companies_for_locations(["Mars"])
        assert len(result) > 50


# ---------------------------------------------------------------------------
# Test: Recommendations Endpoint
# ---------------------------------------------------------------------------


class TestRecommendationsEndpoint:
    async def test_recommendations_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/search/recommendations")
        assert resp.status_code in (401, 403)

    async def test_recommendations_requires_job_prefs(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Returns 400 if user has no target_role set."""
        resp = await client.get("/api/v1/search/recommendations", headers=auth_headers)
        assert resp.status_code == 400
        assert "preferences" in resp.json()["detail"].lower()

    async def test_recommendations_returns_results(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """Happy path: returns recommendations with mocked job fetcher."""
        with patch("app.services.job_recommendations.JobFetcher") as MockCls:
            mock = MockCls.return_value
            mock.fetch_jobs_for_company = AsyncMock(side_effect=_mock_fetch)
            mock.match_jobs_to_role = AsyncMock(side_effect=_mock_match)

            resp = await client.get(
                "/api/v1/search/recommendations", headers=auth_headers
            )

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "recommendations" in data
        assert "scan_stats" in data
        recs = data["recommendations"]
        assert len(recs) > 0

        # Each recommendation has expected fields
        rec = recs[0]
        assert "company" in rec
        assert "display_name" in rec
        assert "matching_openings" in rec
        assert "matching_count" in rec
        assert rec["matching_count"] > 0

    async def test_recommendations_exclude_param(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """Excluded companies are filtered out."""
        with patch("app.services.job_recommendations.JobFetcher") as MockCls:
            mock = MockCls.return_value
            mock.fetch_jobs_for_company = AsyncMock(side_effect=_mock_fetch)
            mock.match_jobs_to_role = AsyncMock(side_effect=_mock_match)

            resp = await client.get(
                "/api/v1/search/recommendations?exclude=grab,stripe",
                headers=auth_headers,
            )

        recs = resp.json()["data"]["recommendations"]
        company_keys = [r["company"] for r in recs]
        assert "grab" not in company_keys
        assert "stripe" not in company_keys

    async def test_recommendations_respects_limit(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """Limit param caps results."""
        with patch("app.services.job_recommendations.JobFetcher") as MockCls:
            mock = MockCls.return_value
            mock.fetch_jobs_for_company = AsyncMock(side_effect=_mock_fetch)
            mock.match_jobs_to_role = AsyncMock(side_effect=_mock_match)

            resp = await client.get(
                "/api/v1/search/recommendations?limit=2",
                headers=auth_headers,
            )

        recs = resp.json()["data"]["recommendations"]
        assert len(recs) <= 2


# ---------------------------------------------------------------------------
# Test: EnrichmentCache round-trip
# ---------------------------------------------------------------------------


class TestRecommendationCache:
    async def test_cache_write_and_read(self):
        """Cached jobs can be written and read back."""
        from app.services.job_recommendations import get_cached_jobs, set_cached_jobs

        async with TestSessionLocal() as db:
            await set_cached_jobs("test-company", MOCK_JOBS, db)
            await db.commit()

            result = await get_cached_jobs("test-company", db)
            assert result is not None
            assert len(result) == 2
            assert result[0]["title"] == "Senior Software Engineer"

    async def test_cache_expired_not_returned(self):
        """Expired cache entries are not returned."""
        from app.services.job_recommendations import get_cached_jobs

        async with TestSessionLocal() as db:
            # Insert an already-expired entry
            db.add(
                EnrichmentCache(
                    cache_key="job_scan:expired-co",
                    source="job_scan",
                    data={"jobs": [{"title": "Old Job"}]},
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
            )
            await db.commit()

            result = await get_cached_jobs("expired-co", db)
            assert result is None
