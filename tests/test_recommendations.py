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
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    from tests.conftest import create_test_user_in_db

    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="rectest@test.com", full_name="Rec Tester"
        )
    return headers


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


def _mock_fetch(name, boards, location_hint=None):
    """Return mock jobs for any company."""
    return MOCK_JOBS


def _mock_match(jobs, role, sen=None, company_name=""):
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

    def test_companies_for_locations_returns_all(self):
        """All companies returned regardless of target location."""
        all_companies = companies_for_locations(None)
        sg_companies = companies_for_locations(["Singapore"])
        us_companies = companies_for_locations(["San Francisco"])
        assert set(all_companies) == set(sg_companies) == set(us_companies)
        assert len(all_companies) > 50

    def test_companies_for_locations_empty_list(self):
        result = companies_for_locations([])
        assert len(result) > 50

    def test_companies_for_locations_unrecognized(self):
        """Unrecognized location still returns all companies."""
        result = companies_for_locations(["Mars"])
        assert len(result) > 50

    def test_companies_for_locations_prioritizes_matched_region(self):
        """Singapore location puts SEA companies before US companies."""
        result = companies_for_locations(["Singapore"])
        grab_idx = result.index("grab")
        stripe_idx = result.index("stripe")
        assert grab_idx < stripe_idx, "SEA company should appear before US company"

    def test_companies_for_locations_us_prioritizes_us(self):
        """US location puts US companies before SEA companies."""
        result = companies_for_locations(["San Francisco"])
        stripe_idx = result.index("stripe")
        grab_idx = result.index("grab")
        assert stripe_idx < grab_idx, "US company should appear before SEA company"


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


# ---------------------------------------------------------------------------
# Test: RecommendationDemandSignal model round-trip
# ---------------------------------------------------------------------------


class TestNetworkFirstCascade:
    async def test_recommendations_include_network_fields(self, client):
        """Recommendations include network_density and network_label fields."""
        from app.models.company import Company
        from app.models.contact import Contact

        async with TestSessionLocal() as db:
            user, headers = await create_test_user_in_db(db, email="netfield@test.com")
            user_id = user.id

        # Set preferences via API (avoids SQLite JSONB server_default issue)
        await client.put(
            "/api/v1/preferences/job",
            headers=headers,
            json={
                "target_role": "Software Engineer",
                "target_locations": ["Singapore"],
            },
        )

        # Seed a company + contact so network layer finds it
        async with TestSessionLocal() as db:
            company = Company(name="Grab", domain="grab.com")
            db.add(company)
            await db.flush()

            contact = Contact(
                user_id=user_id,
                first_name="Test",
                last_name="Contact",
                full_name="Test Contact",
                fingerprint="nettest123",
                company_id=company.id,
            )
            db.add(contact)
            await db.commit()

        resp = await client.get(
            "/api/v1/search/recommendations?limit=10", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        recs = data["recommendations"]

        # Should find Grab with network data (may come from board_registry
        # or network_signal depending on whether the board scan found it)
        grab = next((r for r in recs if r["company"] == "grab"), None)
        assert grab is not None
        assert "network_density" in grab
        assert grab["network_density"] >= 1
        assert "network_label" in grab
        assert grab["source"] in ("network_signal", "board_registry")

    async def test_recommendations_scan_stats_include_network(self, client):
        """scan_stats includes network_matches count."""
        async with TestSessionLocal() as db:
            _user, headers = await create_test_user_in_db(db, email="stats@test.com")

        # Set preferences via API
        await client.put(
            "/api/v1/preferences/job",
            headers=headers,
            json={"target_role": "Designer"},
        )

        resp = await client.get(
            "/api/v1/search/recommendations?limit=5", headers=headers
        )
        assert resp.status_code == 200
        stats = resp.json()["data"]["scan_stats"]
        assert "network_matches" in stats


class TestDemandSignals:
    async def test_create_and_query_demand_signal(self):
        """A demand signal can be persisted and queried back with all fields."""
        from sqlalchemy import select

        from app.models.marketplace import RecommendationDemandSignal
        from tests.conftest import create_test_user_in_db

        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(
                db, email="demand-signal@test.com", full_name="Demand Tester"
            )

            signal = RecommendationDemandSignal(
                company_name="Stripe",
                target_role="Senior Software Engineer",
                target_location="Singapore",
                user_id=user.id,
            )
            db.add(signal)
            await db.commit()

            stmt = select(RecommendationDemandSignal).where(
                RecommendationDemandSignal.user_id == user.id
            )
            result = await db.execute(stmt)
            row = result.scalar_one()

            assert row.company_name == "Stripe"
            assert row.target_role == "Senior Software Engineer"
            assert row.target_location == "Singapore"
            assert row.user_id == user.id
            assert row.id is not None
            assert row.created_at is not None

    async def test_demand_signal_nullable_location(self):
        """target_location is optional and defaults to None."""
        from sqlalchemy import select

        from app.models.marketplace import RecommendationDemandSignal
        from tests.conftest import create_test_user_in_db

        async with TestSessionLocal() as db:
            user, _ = await create_test_user_in_db(
                db, email="demand-noloc@test.com", full_name="No Loc Tester"
            )

            signal = RecommendationDemandSignal(
                company_name="Grab",
                target_role="Product Manager",
                user_id=user.id,
            )
            db.add(signal)
            await db.commit()

            stmt = select(RecommendationDemandSignal).where(
                RecommendationDemandSignal.id == signal.id
            )
            result = await db.execute(stmt)
            row = result.scalar_one()

            assert row.target_location is None
            assert row.company_name == "Grab"


# ---------------------------------------------------------------------------
# Test: Demand Signal Capture (end-to-end via recommendations endpoint)
# ---------------------------------------------------------------------------


class TestDemandSignalCapture:
    async def test_sparse_results_log_demand_signal(self, client: AsyncClient):
        """When recommendations return < 3 results, a demand signal is logged."""
        from sqlalchemy import select

        from app.models.marketplace import RecommendationDemandSignal
        from app.services.job_fetcher import JobFetcher

        async with TestSessionLocal() as db:
            user, headers = await create_test_user_in_db(db)
            user_id = user.id

        # Set preferences via API (avoids SQLite JSONB server_default issue)
        await client.put(
            "/api/v1/preferences/job",
            headers=headers,
            json={
                "target_role": "Quantum Computing Engineer",
                "target_locations": ["Mars"],
            },
        )

        # Mock job fetcher to return empty — ensures sparse results regardless
        # of real ATS API availability.
        with patch.object(
            JobFetcher,
            "fetch_jobs_for_company",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get(
                "/api/v1/search/recommendations?limit=10", headers=headers
            )
        assert resp.status_code == 200

        # Check demand signal was logged
        async with TestSessionLocal() as db:
            result = await db.execute(
                select(RecommendationDemandSignal).where(
                    RecommendationDemandSignal.user_id == user_id
                )
            )
            signals = list(result.scalars().all())
            assert len(signals) >= 1
            assert signals[0].target_role == "Quantum Computing Engineer"
