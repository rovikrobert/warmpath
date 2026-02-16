"""Tests for job board fetching, parsing, deduplication, role matching, and registry."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest_asyncio
from httpx import AsyncClient

from app.services.board_registry import BOARD_REGISTRY, lookup_boards, register_board
from app.services.job_fetcher import JobFetcher

# ---------------------------------------------------------------------------
# Realistic fixtures for Greenhouse and Lever API responses
# ---------------------------------------------------------------------------

GREENHOUSE_RESPONSE = {
    "jobs": [
        {
            "id": 4012345,
            "title": "Senior Software Engineer, Platform",
            "updated_at": "2026-01-15T18:30:00Z",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/4012345",
            "location": {"name": "San Francisco, CA"},
            "departments": [{"id": 100, "name": "Engineering"}],
            "metadata": [],
        },
        {
            "id": 4012346,
            "title": "Product Manager, Growth",
            "updated_at": "2026-02-01T12:00:00Z",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/4012346",
            "location": {"name": "Remote (US)"},
            "departments": [{"id": 200, "name": "Product"}],
            "metadata": [],
        },
        {
            "id": 4012347,
            "title": "Staff Data Scientist",
            "updated_at": "2026-01-20T09:00:00Z",
            "absolute_url": "https://boards.greenhouse.io/stripe/jobs/4012347",
            "location": {"name": "New York, NY"},
            "departments": [{"id": 300, "name": "Data Science"}],
            "metadata": [],
        },
    ]
}

LEVER_RESPONSE = [
    {
        "id": "abc-lever-001",
        "text": "Engineering Manager, Infrastructure",
        "hostedUrl": "https://jobs.lever.co/notionhq/abc-lever-001",
        "createdAt": 1705334400000,  # 2024-01-15T12:00:00Z
        "categories": {
            "team": "Engineering",
            "location": "San Francisco, CA",
            "commitment": "Full-time",
        },
    },
    {
        "id": "abc-lever-002",
        "text": "Senior Product Designer",
        "hostedUrl": "https://jobs.lever.co/notionhq/abc-lever-002",
        "createdAt": 1706544000000,  # 2024-01-29T12:00:00Z
        "categories": {
            "team": "Design",
            "location": "Remote - Anywhere",
            "commitment": "Full-time",
        },
    },
]


# ---------------------------------------------------------------------------
# Helper to create a mock httpx response
# ---------------------------------------------------------------------------


def _mock_response(json_data, status_code=200):
    resp = httpx.Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://example.com"),
    )
    return resp


# ---------------------------------------------------------------------------
# Test Greenhouse Parsing
# ---------------------------------------------------------------------------


class TestGreenhouseFetcher:

    async def test_parses_jobs_correctly(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=_mock_response(GREENHOUSE_RESPONSE)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_greenhouse_jobs("stripe")

        assert len(jobs) == 3
        assert jobs[0]["title"] == "Senior Software Engineer, Platform"
        assert jobs[0]["source"] == "greenhouse"
        assert jobs[0]["source_job_id"] == "4012345"
        assert jobs[0]["department"] == "Engineering"
        assert jobs[0]["location"] == "San Francisco, CA"
        assert jobs[0]["url"] == "https://boards.greenhouse.io/stripe/jobs/4012345"
        assert jobs[0]["is_remote"] is False


    async def test_detects_remote(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=_mock_response(GREENHOUSE_RESPONSE)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_greenhouse_jobs("stripe")

        # Job at index 1 has "Remote (US)" location
        assert jobs[1]["is_remote"] is True
        assert jobs[0]["is_remote"] is False
        assert jobs[2]["is_remote"] is False


    async def test_handles_http_error(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_greenhouse_jobs("nonexistent")

        assert jobs == []


# ---------------------------------------------------------------------------
# Test Lever Parsing
# ---------------------------------------------------------------------------


class TestLeverFetcher:

    async def test_parses_jobs_correctly(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(LEVER_RESPONSE))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_lever_jobs("notionhq")

        assert len(jobs) == 2
        assert jobs[0]["title"] == "Engineering Manager, Infrastructure"
        assert jobs[0]["source"] == "lever"
        assert jobs[0]["source_job_id"] == "abc-lever-001"
        assert jobs[0]["department"] == "Engineering"
        assert jobs[0]["location"] == "San Francisco, CA"
        assert jobs[0]["is_remote"] is False


    async def test_detects_remote_lever(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(LEVER_RESPONSE))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_lever_jobs("notionhq")

        # Job at index 1 has "Remote - Anywhere"
        assert jobs[1]["is_remote"] is True
        assert jobs[0]["is_remote"] is False


    async def test_handles_http_error(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=httpx.HTTPError("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_lever_jobs("badslug")

        assert jobs == []


# ---------------------------------------------------------------------------
# Test Role Matching (mock mode)
# ---------------------------------------------------------------------------


class TestRoleMatching:

    async def test_mock_match_keyword_overlap(self):
        fetcher = JobFetcher()
        jobs = [
            {"title": "Senior Software Engineer", "department": "Engineering"},
            {"title": "Product Manager, Growth", "department": "Product"},
            {"title": "Staff Software Engineer, Platform", "department": "Engineering"},
            {"title": "Sales Development Representative", "department": "Sales"},
        ]
        matched = await fetcher.match_jobs_to_role(jobs, "Software Engineer")
        titles = [j["title"] for j in matched]
        assert "Senior Software Engineer" in titles
        # Staff SWE may or may not meet threshold depending on word overlap
        # but SDR definitely should not match
        assert "Sales Development Representative" not in titles
        assert len(matched) >= 1


    async def test_mock_match_with_seniority(self):
        fetcher = JobFetcher()
        jobs = [
            {"title": "Senior Software Engineer", "department": "Engineering"},
            {"title": "Junior Software Engineer", "department": "Engineering"},
            {"title": "Software Engineer", "department": "Engineering"},
        ]
        matched = await fetcher.match_jobs_to_role(
            jobs, "Software Engineer", target_seniority="Senior"
        )
        # Senior match should appear and score higher
        assert any("Senior" in j["title"] for j in matched)


    async def test_empty_inputs(self):
        fetcher = JobFetcher()
        assert await fetcher.match_jobs_to_role([], "Engineer") == []
        assert await fetcher.match_jobs_to_role([{"title": "Eng"}], "") == []


# ---------------------------------------------------------------------------
# Test Board Registry
# ---------------------------------------------------------------------------


class TestBoardRegistry:
    def test_exact_lookup(self):
        boards = lookup_boards("stripe")
        assert boards is not None
        assert boards["greenhouse"] == "stripe"

    def test_case_insensitive_lookup(self):
        boards = lookup_boards("Stripe")
        assert boards is not None
        assert boards["greenhouse"] == "stripe"

    def test_fuzzy_lookup(self):
        # "stripee" is close enough to "stripe" (> 0.8 similarity)
        boards = lookup_boards("stripee")
        # May or may not match depending on threshold — just test it doesn't crash
        # SequenceMatcher("stripe", "stripee") ≈ 0.923
        assert boards is not None

    def test_no_match(self):
        boards = lookup_boards("completely_unknown_company_xyz")
        assert boards is None

    def test_register_new_board(self):
        register_board("TestCorp", "greenhouse", "testcorp")
        boards = lookup_boards("testcorp")
        assert boards is not None
        assert boards["greenhouse"] == "testcorp"
        # Clean up
        del BOARD_REGISTRY["testcorp"]

    def test_register_adds_to_existing(self):
        register_board("TestCo2", "greenhouse", "testco2")
        register_board("TestCo2", "lever", "testco2lever")
        boards = lookup_boards("testco2")
        assert boards is not None
        assert boards["greenhouse"] == "testco2"
        assert boards["lever"] == "testco2lever"
        del BOARD_REGISTRY["testco2"]


# ---------------------------------------------------------------------------
# Test API Endpoints — Deduplication and Integration
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Create a test user and return auth headers."""
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "jobtest@test.com",
            "password": "testpass123",
            "full_name": "Job Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "jobtest@test.com", "password": "testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestJobsAPI:

    async def test_scan_unknown_company(self, client: AsyncClient, auth_headers):
        resp = await client.get(
            "/api/v1/jobs/scan/completely_unknown_xyz",
            headers=auth_headers,
        )
        assert resp.status_code == 404


    async def test_scan_and_dedup(self, client: AsyncClient, auth_headers):
        """Scanning the same company twice should not create duplicate openings."""
        with patch.object(
            JobFetcher,
            "fetch_jobs_for_company",
            return_value=[
                {
                    "title": "Software Engineer",
                    "department": "Engineering",
                    "location": "SF",
                    "url": "https://example.com/jobs/1",
                    "source": "greenhouse",
                    "source_job_id": "dedup-001",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                },
                {
                    "title": "Product Manager",
                    "department": "Product",
                    "location": "NYC",
                    "url": "https://example.com/jobs/2",
                    "source": "greenhouse",
                    "source_job_id": "dedup-002",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                },
            ],
        ):
            # First scan
            resp1 = await client.get("/api/v1/jobs/scan/stripe", headers=auth_headers)
            assert resp1.status_code == 200
            assert resp1.json()["meta"]["openings_count"] == 2

            # Second scan — same jobs, should upsert not duplicate
            resp2 = await client.get("/api/v1/jobs/scan/stripe", headers=auth_headers)
            assert resp2.status_code == 200
            assert resp2.json()["meta"]["openings_count"] == 2

        # Verify via list endpoint — still just 2
        resp3 = await client.get("/api/v1/jobs/openings", headers=auth_headers)
        assert resp3.status_code == 200
        assert len(resp3.json()["data"]) == 2


    async def test_list_openings_filter_by_role(
        self, client: AsyncClient, auth_headers
    ):
        """Test filtering openings by role keyword."""
        with patch.object(
            JobFetcher,
            "fetch_jobs_for_company",
            return_value=[
                {
                    "title": "Senior Software Engineer",
                    "department": "Eng",
                    "location": "SF",
                    "url": "https://example.com/jobs/10",
                    "source": "greenhouse",
                    "source_job_id": "role-001",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                },
                {
                    "title": "Marketing Manager",
                    "department": "Marketing",
                    "location": "NYC",
                    "url": "https://example.com/jobs/11",
                    "source": "greenhouse",
                    "source_job_id": "role-002",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                },
            ],
        ):
            await client.get("/api/v1/jobs/scan/stripe", headers=auth_headers)

        # Filter by "engineer"
        resp = await client.get(
            "/api/v1/jobs/openings?role=engineer", headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert "Engineer" in data[0]["title"]


    async def test_scan_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/jobs/scan/stripe")
        assert resp.status_code in (401, 403)
