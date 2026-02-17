"""Tests for dashboard insights endpoint and supporting helpers."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient

from app.models.enrichment import EnrichmentCache
from app.services.dashboard_insights import TIPS, _get_daily_tip
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
            "email": "dashtest@test.com",
            "password": "Testpass123",
            "full_name": "Dash Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "dashtest@test.com", "password": "Testpass123"},
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


@pytest_asyncio.fixture
async def user_with_contacts(auth_headers: dict, client: AsyncClient) -> dict:
    """Create several manual contacts and return auth headers."""
    contacts_data = [
        {
            "first_name": "Alice",
            "last_name": "Eng",
            "company": "Google",
            "position": "SWE",
            "relationship_type": "current_colleague",
        },
        {
            "first_name": "Bob",
            "last_name": "Eng",
            "company": "Google",
            "position": "SRE",
            "relationship_type": "current_colleague",
        },
        {
            "first_name": "Carol",
            "last_name": "PM",
            "company": "Stripe",
            "position": "PM",
            "relationship_type": "friend",
        },
        {
            "first_name": "Dave",
            "last_name": "DS",
            "company": "Stripe",
            "position": "Data Scientist",
            "relationship_type": "current_colleague",
        },
        {
            "first_name": "Eve",
            "last_name": "Mgr",
            "company": "Stripe",
            "position": "Eng Manager",
            "relationship_type": "manager",
        },
        {
            "first_name": "Frank",
            "last_name": "Dev",
            "company": "Airbnb",
            "position": "SWE",
            "relationship_type": "current_colleague",
        },
        {
            "first_name": "Grace",
            "last_name": "Rec",
            "company": "Meta",
            "position": "Recruiter",
            "relationship_type": "recruiter",
        },
    ]
    await client.post(
        "/api/v1/contacts/manual/bulk",
        headers=auth_headers,
        json={"contacts": contacts_data},
    )
    return auth_headers


# Mock recommendation data
MOCK_RECS = {
    "recommendations": [
        {
            "company": "stripe",
            "display_name": "Stripe",
            "region": "US / Global",
            "matching_openings": [
                {
                    "title": "Senior SWE",
                    "url": "",
                    "location": "SG",
                    "is_remote": False,
                    "relevance": 90,
                }
            ],
            "matching_count": 3,
            "total_openings": 10,
            "top_titles": ["Senior SWE", "Staff SWE"],
            "score": 270,
            "source": "board_registry",
        },
        {
            "company": "grab",
            "display_name": "Grab",
            "region": "Singapore / SEA",
            "matching_openings": [
                {
                    "title": "Software Engineer",
                    "url": "",
                    "location": "SG",
                    "is_remote": False,
                    "relevance": 85,
                }
            ],
            "matching_count": 2,
            "total_openings": 8,
            "top_titles": ["Software Engineer", "Backend Engineer"],
            "score": 170,
            "source": "board_registry",
        },
    ],
    "scan_stats": {
        "companies_scanned": 15,
        "cache_hits": 10,
        "fresh_scans": 5,
    },
}


# ---------------------------------------------------------------------------
# Test: Dashboard Insights Endpoint
# ---------------------------------------------------------------------------


class TestDashboardInsightsEndpoint:
    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/dashboard/insights")
        assert resp.status_code in (401, 403)

    async def test_returns_200_no_prefs_no_contacts(
        self, client: AsyncClient, auth_headers: dict
    ):
        """With no preferences and no contacts, only daily tip is populated."""
        resp = await client.get("/api/v1/dashboard/insights", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["job_market_trends"] is None
        assert data["network_analysis"] is None
        assert data["daily_tip"] is not None
        assert "tip" in data["daily_tip"]
        assert "category" in data["daily_tip"]

    async def test_returns_trends_with_prefs(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """With preferences set, trends are populated via mocked recommendations."""
        with patch(
            "app.services.job_recommendations.get_recommendations",
            new_callable=AsyncMock,
            return_value=MOCK_RECS,
        ):
            resp = await client.get("/api/v1/dashboard/insights", headers=auth_headers)

        assert resp.status_code == 200
        trends = resp.json()["data"]["job_market_trends"]
        assert trends is not None
        assert trends["companies_hiring"] == 2
        assert "hiring" in trends["summary"].lower()
        assert len(trends["trending_titles"]) > 0

    async def test_returns_network_analysis(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        """With contacts created, network analysis is populated."""
        resp = await client.get(
            "/api/v1/dashboard/insights", headers=user_with_contacts
        )
        assert resp.status_code == 200
        network = resp.json()["data"]["network_analysis"]
        assert network is not None
        assert network["total_contacts"] == 7
        # Stripe has 3 contacts, Google has 2
        top = network["top_companies"]
        assert top[0]["company"] == "Stripe"
        assert top[0]["count"] == 3
        assert top[1]["company"] == "Google"
        assert top[1]["count"] == 2

    async def test_response_envelope(self, client: AsyncClient, auth_headers: dict):
        """Verify standard {data, meta} envelope."""
        resp = await client.get("/api/v1/dashboard/insights", headers=auth_headers)
        body = resp.json()
        assert "data" in body
        assert "meta" in body
        assert "generated_at" in body["data"]

    async def test_trends_personalized_with_recent_searches(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """Summary mentions user's searched companies when they match hiring results."""
        # Create a search that targets "Stripe"
        await client.post(
            "/api/v1/search",
            headers=auth_headers,
            json={
                "name": "Smart Search: SWE at Stripe",
                "target_companies": ["Stripe"],
                "target_role": "Software Engineer",
            },
        )

        with patch(
            "app.services.job_recommendations.get_recommendations",
            new_callable=AsyncMock,
            return_value=MOCK_RECS,
        ):
            resp = await client.get("/api/v1/dashboard/insights", headers=auth_headers)

        trends = resp.json()["data"]["job_market_trends"]
        assert trends is not None
        # Stripe should be called out by name since user searched for it
        assert "Stripe" in trends["summary"]
        assert "Stripe" in trends["searched_and_hiring"]


# ---------------------------------------------------------------------------
# Test: Daily Tip
# ---------------------------------------------------------------------------


class TestDailyTip:
    def test_tip_rotates_by_day(self):
        """Different days give different tips."""
        tip1 = _get_daily_tip(day_of_year=1)
        tip2 = _get_daily_tip(day_of_year=2)
        assert tip1["tip"] != tip2["tip"]

    def test_tip_wraps_around(self):
        """Day N == day N + len(tips)."""
        n = 5
        tip_a = _get_daily_tip(day_of_year=n)
        tip_b = _get_daily_tip(day_of_year=n + len(TIPS))
        assert tip_a["tip"] == tip_b["tip"]
        assert tip_a["category"] == tip_b["category"]

    def test_tip_has_required_fields(self):
        tip = _get_daily_tip(day_of_year=0)
        assert "tip" in tip
        assert "category" in tip
        assert "day_index" in tip
        assert isinstance(tip["tip"], str)
        assert len(tip["tip"]) > 10


# ---------------------------------------------------------------------------
# Test: Insights Cache
# ---------------------------------------------------------------------------


class TestInsightsCache:
    async def test_trends_cached(
        self, client: AsyncClient, auth_headers: dict, prefs_set: None
    ):
        """Second call to insights reuses cache — doesn't call get_recommendations again."""
        mock_rec = AsyncMock(return_value=MOCK_RECS)
        with patch(
            "app.services.job_recommendations.get_recommendations",
            mock_rec,
        ):
            # First call — populates cache
            resp1 = await client.get("/api/v1/dashboard/insights", headers=auth_headers)
            assert resp1.status_code == 200
            assert resp1.json()["data"]["job_market_trends"] is not None

            # Second call — should hit cache
            resp2 = await client.get("/api/v1/dashboard/insights", headers=auth_headers)
            assert resp2.status_code == 200
            assert resp2.json()["data"]["job_market_trends"] is not None

        # get_recommendations should only be called once
        assert mock_rec.call_count == 1

    async def test_network_cache_expires(self):
        """Expired cache entry returns None from _read_cache."""
        from app.services.dashboard_insights import _read_cache

        async with TestSessionLocal() as db:
            # Insert an expired entry
            db.add(
                EnrichmentCache(
                    cache_key="dashboard_network:expired-user",
                    source="dashboard_insights",
                    data={"summary": "old data"},
                    expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
            )
            await db.commit()

            result = await _read_cache("dashboard_network:expired-user", db)
            assert result is None


# ---------------------------------------------------------------------------
# Test: Network Analysis
# ---------------------------------------------------------------------------


class TestNetworkAnalysis:
    async def test_empty_contacts_returns_none(
        self, client: AsyncClient, auth_headers: dict
    ):
        """No contacts means network_analysis is None."""
        resp = await client.get("/api/v1/dashboard/insights", headers=auth_headers)
        assert resp.json()["data"]["network_analysis"] is None

    async def test_relationship_breakdown(
        self, client: AsyncClient, user_with_contacts: dict
    ):
        """Verify relationship type grouping counts."""
        resp = await client.get(
            "/api/v1/dashboard/insights", headers=user_with_contacts
        )
        network = resp.json()["data"]["network_analysis"]
        breakdown = network["relationship_breakdown"]
        assert breakdown["current_colleague"] == 4
        assert breakdown["friend"] == 1
        assert breakdown["manager"] == 1
        assert breakdown["recruiter"] == 1
