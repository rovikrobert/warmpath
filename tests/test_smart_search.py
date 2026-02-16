"""Tests for job preferences CRUD and smart search endpoint."""

import uuid as uuid_mod
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from httpx import AsyncClient

from app.models.contact import Contact
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
            "email": "smarttest@test.com",
            "password": "Testpass123",
            "full_name": "Smart Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "smarttest@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def contacts_at_companies(user_id: str) -> None:
    """Create test contacts at Stripe, Notion, and Figma."""
    uid = uuid_mod.UUID(user_id)
    async with TestSessionLocal() as db:
        db.add(
            Contact(
                user_id=uid,
                full_name="Alice Stripe",
                first_name="Alice",
                last_name="Stripe",
                current_company="Stripe",
                current_title="Senior Software Engineer",
                location="San Francisco, CA",
            )
        )
        db.add(
            Contact(
                user_id=uid,
                full_name="Bob Stripe",
                first_name="Bob",
                last_name="Stripe",
                current_company="Stripe",
                current_title="Engineering Manager",
                location="New York, NY",
            )
        )
        db.add(
            Contact(
                user_id=uid,
                full_name="Charlie Notion",
                first_name="Charlie",
                last_name="Notion",
                current_company="Notion",
                current_title="Product Manager",
                location="San Francisco, CA",
            )
        )
        db.add(
            Contact(
                user_id=uid,
                full_name="Diana Figma",
                first_name="Diana",
                last_name="Figma",
                current_company="Figma",
                current_title="Staff Designer",
                location="London, UK",
            )
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Test Job Preferences CRUD
# ---------------------------------------------------------------------------


class TestJobPreferences:
    async def test_create_preferences(self, client: AsyncClient, auth_headers: dict):
        resp = await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={
                "target_role": "Software Engineer",
                "target_seniority": "Senior",
                "target_locations": ["San Francisco", "New York"],
                "open_to_remote": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["target_role"] == "Software Engineer"
        assert data["target_seniority"] == "Senior"
        assert data["open_to_remote"] is True

    async def test_get_preferences(self, client: AsyncClient, auth_headers: dict):
        # Set first
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Product Manager"},
        )

        # Get
        resp = await client.get("/api/v1/preferences/job", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["target_role"] == "Product Manager"

    async def test_get_without_setting(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/preferences/job", headers=auth_headers)
        assert resp.status_code == 404

    async def test_upsert_updates_existing(
        self, client: AsyncClient, auth_headers: dict
    ):
        # Create
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Designer"},
        )

        # Update
        resp = await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={
                "target_role": "Senior Designer",
                "salary_min": 150000,
                "salary_max": 250000,
            },
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["target_role"] == "Senior Designer"
        assert data["salary_min"] == 150000
        assert data["salary_max"] == 250000

    async def test_delete_preferences(self, client: AsyncClient, auth_headers: dict):
        # Create
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Engineer"},
        )

        # Delete
        resp = await client.delete("/api/v1/preferences/job", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] is True

        # Confirm gone
        resp = await client.get("/api/v1/preferences/job", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_nonexistent(self, client: AsyncClient, auth_headers: dict):
        resp = await client.delete("/api/v1/preferences/job", headers=auth_headers)
        assert resp.status_code == 404

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/preferences/job")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Test Smart Search
# ---------------------------------------------------------------------------


MOCK_STRIPE_JOBS = [
    {
        "title": "Senior Software Engineer, Platform",
        "department": "Engineering",
        "location": "San Francisco, CA",
        "url": "https://boards.greenhouse.io/stripe/jobs/1",
        "source": "greenhouse",
        "source_job_id": "smart-001",
        "posted_at": None,
        "is_remote": False,
        "raw_data": {},
        "role_relevance": 85,
    },
    {
        "title": "Staff Software Engineer",
        "department": "Engineering",
        "location": "Remote (US)",
        "url": "https://boards.greenhouse.io/stripe/jobs/2",
        "source": "greenhouse",
        "source_job_id": "smart-002",
        "posted_at": None,
        "is_remote": True,
        "raw_data": {},
        "role_relevance": 70,
    },
]

MOCK_NOTION_JOBS = [
    {
        "title": "Product Designer",
        "department": "Design",
        "location": "San Francisco, CA",
        "url": "https://jobs.lever.co/notion/1",
        "source": "lever",
        "source_job_id": "smart-003",
        "posted_at": None,
        "is_remote": False,
        "raw_data": {},
        "role_relevance": 50,
    },
]


class TestSmartSearch:
    async def test_requires_preferences(self, client: AsyncClient, auth_headers: dict):
        """Smart search fails without job preferences set."""
        resp = await client.post(
            "/api/v1/search/smart",
            headers=auth_headers,
            json={"company_names": ["Stripe"]},
        )
        assert resp.status_code == 400
        assert "preferences" in resp.json()["detail"].lower()

    async def test_smart_search_with_openings_and_contacts(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Full smart search with mocked job fetcher."""
        # Set preferences
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer", "target_seniority": "Senior"},
        )

        with (
            patch.object(
                "app.services.job_fetcher.JobFetcher",
                "fetch_jobs_for_company",
                new_callable=AsyncMock,
                return_value=MOCK_STRIPE_JOBS,
            )
            if False
            else patch("app.api.search.JobFetcher") as MockFetcherClass,
        ):
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(
                side_effect=lambda name, boards: (
                    MOCK_STRIPE_JOBS
                    if "stripe" in name.lower()
                    else MOCK_NOTION_JOBS
                    if "notion" in name.lower()
                    else []
                )
            )
            mock_fetcher.match_jobs_to_role = AsyncMock(
                side_effect=lambda jobs, role, sen=None: jobs
            )

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe", "Notion", "Figma"]},
            )

        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["status"] == "completed"
        assert "companies" in data
        assert "summary" in data

        companies = data["companies"]
        assert len(companies) == 3

        summary = data["summary"]
        assert summary["companies_searched"] == 3

    async def test_companies_with_both_sort_first(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Companies with openings + referral paths sort above others."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            # Only Stripe has openings; Notion and Figma don't
            mock_fetcher.fetch_jobs_for_company = AsyncMock(
                side_effect=lambda name, boards: (
                    MOCK_STRIPE_JOBS if "stripe" in name.lower() else []
                )
            )
            mock_fetcher.match_jobs_to_role = AsyncMock(
                side_effect=lambda jobs, role, sen=None: jobs
            )

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Notion", "Stripe", "Figma"]},
            )

        data = resp.json()["data"]
        companies = data["companies"]

        # Stripe has both openings and referral paths (Alice, Bob work there)
        # So Stripe should be first
        stripe = next(c for c in companies if c["name"] == "Stripe")
        assert stripe["has_openings"] is True
        assert stripe["has_referral_paths"] is True

        # Stripe should be sorted first
        assert companies[0]["name"] == "Stripe"

    async def test_referral_paths_include_cultural_context(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Referral paths include cultural context and warm scores."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(return_value=[])
            mock_fetcher.match_jobs_to_role = AsyncMock(return_value=[])

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe"]},
            )

        data = resp.json()["data"]
        stripe = data["companies"][0]
        assert stripe["name"] == "Stripe"
        assert stripe["has_referral_paths"] is True

        path = stripe["referral_paths"][0]
        assert "contact" in path
        assert "cultural_context" in path
        assert "recommended_channel" in path
        assert path["source"] == "own_network"
        assert "warm_score" in path["contact"]
        assert "referral_likelihood" in path["contact"]

    async def test_source_field_present(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Every company result includes source = 'own_network'."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(return_value=[])
            mock_fetcher.match_jobs_to_role = AsyncMock(return_value=[])

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe", "Notion"]},
            )

        for company in resp.json()["data"]["companies"]:
            assert company["source"] == "own_network"

    async def test_progress_tracking(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Smart search creates a SearchRequest that can be polled."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(return_value=[])
            mock_fetcher.match_jobs_to_role = AsyncMock(return_value=[])

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe"]},
            )

        assert resp.status_code == 201
        search_id = resp.json()["data"]["id"]

        # Poll the search — should be completed
        poll_resp = await client.get(
            f"/api/v1/search/{search_id}", headers=auth_headers
        )
        assert poll_resp.status_code == 200
        poll_data = poll_resp.json()["data"]
        assert poll_data["status"] == "completed"
        assert "results_data" in poll_data
        assert poll_data["results_data"]["summary"]["companies_searched"] == 1

    async def test_company_without_contacts(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Company with no contacts in user's network has empty referral_paths."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(
                return_value=MOCK_STRIPE_JOBS
            )
            mock_fetcher.match_jobs_to_role = AsyncMock(
                side_effect=lambda jobs, role, sen=None: jobs
            )

            resp = await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe"]},
            )

        data = resp.json()["data"]
        stripe = data["companies"][0]
        assert stripe["has_openings"] is True
        assert stripe["has_referral_paths"] is False
        assert stripe["referral_paths"] == []

    async def test_smart_search_requires_auth(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/search/smart",
            json={"company_names": ["Stripe"]},
        )
        assert resp.status_code in (401, 403)

    async def test_search_appears_in_list(
        self,
        client: AsyncClient,
        auth_headers: dict,
        contacts_at_companies: None,
    ):
        """Smart search creates a SearchRequest visible in the list endpoint."""
        await client.put(
            "/api/v1/preferences/job",
            headers=auth_headers,
            json={"target_role": "Software Engineer"},
        )

        with patch("app.api.search.JobFetcher") as MockFetcherClass:
            mock_fetcher = MockFetcherClass.return_value
            mock_fetcher.fetch_jobs_for_company = AsyncMock(return_value=[])
            mock_fetcher.match_jobs_to_role = AsyncMock(return_value=[])

            await client.post(
                "/api/v1/search/smart",
                headers=auth_headers,
                json={"company_names": ["Stripe"]},
            )

        resp = await client.get("/api/v1/search", headers=auth_headers)
        assert resp.status_code == 200
        searches = resp.json()["data"]
        assert len(searches) >= 1
        assert any("Smart search" in s["name"] for s in searches)
