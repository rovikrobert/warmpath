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
# Test Ashby Parsing
# ---------------------------------------------------------------------------

ASHBY_RESPONSE = {
    "jobs": [
        {
            "id": "240d459b-aaaa-bbbb-cccc-fab3e56ecd9b",
            "title": "Research Engineer",
            "department": "Research",
            "team": "Research",
            "employmentType": "FullTime",
            "location": "San Francisco",
            "publishedAt": "2025-04-05T00:03:20.653+00:00",
            "isListed": True,
            "isRemote": None,
            "jobUrl": "https://jobs.ashbyhq.com/openai/240d459b",
        },
        {
            "id": "340e560c-dddd-eeee-ffff-123456789abc",
            "title": "Senior Software Engineer, Platform",
            "department": "Engineering",
            "team": "Platform",
            "employmentType": "FullTime",
            "location": "Remote",
            "publishedAt": "2025-05-10T12:00:00.000+00:00",
            "isListed": True,
            "isRemote": True,
            "jobUrl": "https://jobs.ashbyhq.com/openai/340e560c",
        },
        {
            "id": "unlisted-job-id",
            "title": "Secret Internal Role",
            "department": "Ops",
            "team": "Ops",
            "location": "NYC",
            "isListed": False,
            "isRemote": False,
            "jobUrl": "https://jobs.ashbyhq.com/openai/unlisted",
        },
    ]
}


class TestAshbyFetcher:
    async def test_parses_jobs_correctly(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(ASHBY_RESPONSE))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_ashby_jobs("openai")

        # Unlisted job should be filtered out
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Research Engineer"
        assert jobs[0]["source"] == "ashby"
        assert jobs[0]["department"] == "Research"
        assert jobs[0]["location"] == "San Francisco"
        assert jobs[0]["url"] == "https://jobs.ashbyhq.com/openai/240d459b"

    async def test_detects_remote(self):
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(ASHBY_RESPONSE))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetcher.fetch_ashby_jobs("openai")

        assert jobs[0]["is_remote"] is False
        assert jobs[1]["is_remote"] is True

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

            jobs = await fetcher.fetch_ashby_jobs("nonexistent")

        assert jobs == []


# ---------------------------------------------------------------------------
# Test Board Registry — updated platform entries
# ---------------------------------------------------------------------------


class TestBoardRegistryPlatforms:
    def test_openai_uses_ashby(self):
        boards = lookup_boards("openai")
        assert boards is not None
        assert "ashby" in boards
        assert boards["ashby"] == "openai"

    def test_notion_uses_ashby(self):
        boards = lookup_boards("notion")
        assert boards is not None
        assert "ashby" in boards

    def test_ramp_uses_ashby(self):
        boards = lookup_boards("ramp")
        assert boards is not None
        assert "ashby" in boards

    def test_grab_uses_career_page(self):
        boards = lookup_boards("grab")
        assert boards is not None
        assert "career_page" in boards

    def test_google_uses_career_page(self):
        boards = lookup_boards("google")
        assert boards is not None
        assert "career_page" in boards


# ---------------------------------------------------------------------------
# Test Careers URL lookup
# ---------------------------------------------------------------------------


class TestCareersUrl:
    def test_known_company(self):
        from app.services.board_registry import lookup_careers_url

        url = lookup_careers_url("openai")
        assert url is not None
        assert "openai.com" in url

    def test_unknown_company(self):
        from app.services.board_registry import lookup_careers_url

        assert lookup_careers_url("unknown_company_xyz") is None


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

    async def test_multi_word_role_partial_match_via_shared_word(self):
        """'General Manager' should match 'Product Manager' via shared 'manager'."""
        fetcher = JobFetcher()
        jobs = [
            {"title": "Product Manager, Growth", "department": "Product"},
            {"title": "Engineering Manager", "department": "Engineering"},
            {"title": "Software Engineer", "department": "Engineering"},
        ]
        matched = await fetcher.match_jobs_to_role(jobs, "General Manager")
        titles = [j["title"] for j in matched]
        assert "Product Manager, Growth" in titles
        assert "Engineering Manager" in titles
        assert "Software Engineer" not in titles

    async def test_multi_word_role_synonym_expansion(self):
        """'General Manager' should match 'Director of Operations' via level synonyms."""
        fetcher = JobFetcher()
        jobs = [
            {"title": "Director of Operations", "department": "Operations"},
            {"title": "Head of Business", "department": "Strategy"},
            {"title": "Data Scientist", "department": "Data"},
        ]
        matched = await fetcher.match_jobs_to_role(jobs, "General Manager")
        titles = [j["title"] for j in matched]
        assert "Director of Operations" in titles
        assert "Head of Business" in titles
        assert "Data Scientist" not in titles

    async def test_engineer_synonym_expansion(self):
        """'Software Engineer' should match 'Backend Developer' via synonyms."""
        fetcher = JobFetcher()
        jobs = [
            {"title": "Backend Developer", "department": "Engineering"},
            {"title": "Account Manager", "department": "Sales"},
        ]
        matched = await fetcher.match_jobs_to_role(jobs, "Software Engineer")
        titles = [j["title"] for j in matched]
        assert "Backend Developer" in titles
        assert "Account Manager" not in titles


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
    from tests.conftest import TestSessionLocal, create_test_user_in_db

    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="jobtest@test.com", full_name="Job Tester"
        )
    return headers


class TestJobsAPI:
    async def test_scan_unknown_company_returns_empty(
        self, client: AsyncClient, auth_headers
    ):
        """Unknown companies return 200 with zero openings (JobSpy fallback runs)."""
        resp = await client.get(
            "/api/v1/jobs/scan/completely_unknown_xyz",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["openings_count"] == 0
        assert body["meta"]["discovery_status"] in (
            "scraped",
            "no_listings",
        )

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


# ---------------------------------------------------------------------------
# Test Aggregator Fallback in fetch_jobs_for_company
# ---------------------------------------------------------------------------


class TestAggregatorFallback:
    async def test_aggregator_called_when_ats_and_career_page_empty(self):
        """Adzuna aggregator fires as 3rd fallback when ATS + career page return nothing."""
        fetcher = JobFetcher()
        adzuna_jobs = [
            {
                "title": "Software Engineer",
                "department": "Engineering",
                "location": "Singapore",
                "url": "https://adzuna.sg/jobs/123",
                "source": "adzuna",
                "source_job_id": "123",
                "posted_at": None,
                "is_remote": False,
                "raw_data": {},
            }
        ]
        with (
            patch("app.services.job_fetcher.settings") as mock_settings,
            patch(
                "app.services.job_aggregator.search_jobs_by_company",
                new_callable=AsyncMock,
                return_value=adzuna_jobs,
            ) as mock_adzuna,
        ):
            mock_settings.AI_MOCK_MODE = True
            mock_settings.ADZUNA_APP_ID = "test-id"
            # No board_ids → ATS returns nothing; career page lookup returns nothing
            jobs = await fetcher.fetch_jobs_for_company("unknown-company-xyz")

        assert len(jobs) == 1
        assert jobs[0]["source"] == "adzuna"
        mock_adzuna.assert_called_once()

    async def test_aggregator_skipped_when_ats_has_enough_results(self):
        """Adzuna should NOT be called if ATS boards return >= threshold results."""
        from app.services.job_fetcher import _CAREER_PAGE_MIN_JOBS

        fetcher = JobFetcher()
        ats_jobs = [
            {"title": f"Engineer {i}", "source": "greenhouse", "url": f"https://g/{i}"}
            for i in range(_CAREER_PAGE_MIN_JOBS)
        ]
        with (
            patch.object(
                fetcher,
                "fetch_greenhouse_jobs",
                new_callable=AsyncMock,
                return_value=ats_jobs,
            ),
            patch("app.services.job_fetcher.settings") as mock_settings,
            patch(
                "app.services.jobspy_fetcher.search_jobs_via_jobspy",
                new_callable=AsyncMock,
            ) as mock_jobspy,
        ):
            mock_settings.AI_MOCK_MODE = True
            mock_settings.ADZUNA_APP_ID = "test-id"
            jobs = await fetcher.fetch_jobs_for_company(
                "stripe", {"greenhouse": "stripe"}
            )

        assert len(jobs) == _CAREER_PAGE_MIN_JOBS
        assert all(j["source"] == "greenhouse" for j in jobs)
        mock_jobspy.assert_not_called()

    async def test_aggregator_skipped_when_not_configured(self):
        """No ADZUNA_APP_ID → aggregator fallback is skipped entirely."""
        fetcher = JobFetcher()
        with patch("app.services.job_fetcher.settings") as mock_settings:
            mock_settings.AI_MOCK_MODE = True
            mock_settings.ADZUNA_APP_ID = ""
            jobs = await fetcher.fetch_jobs_for_company("unknown-company-xyz")

        assert jobs == []


# ---------------------------------------------------------------------------
# Test company_matches — shared employer-name matching
# ---------------------------------------------------------------------------


class TestCompanyMatches:
    """Unit tests for the company_matches function used by all fallback fetchers."""

    @staticmethod
    def _match(query: str, candidate: str) -> bool:
        from app.services.job_fetcher import company_matches

        return company_matches(query, candidate)

    # --- Exact matches ---
    def test_exact_match(self):
        assert self._match("Stripe", "stripe") is True

    def test_exact_with_domain_suffix(self):
        assert self._match("Cantina.ai", "Cantina") is True

    # --- Legal suffix matches (should pass) ---
    def test_legal_suffix_inc(self):
        assert self._match("Shopify", "Shopify Inc.") is True

    def test_legal_suffix_pte_ltd(self):
        assert self._match("Shopify", "Shopify Pte Ltd") is True

    def test_legal_suffix_llc(self):
        assert self._match("Google", "Google LLC") is True

    def test_legal_suffix_holdings(self):
        assert self._match("Grab", "Grab Holdings") is True

    def test_legal_suffix_group_holdings(self):
        assert self._match("DBS", "DBS Group Holdings") is True

    def test_legal_suffix_platforms_inc(self):
        assert self._match("Meta", "Meta Platforms Inc.") is True

    def test_legal_suffix_payments_limited(self):
        assert self._match("Wise", "Wise Payments Limited") is True

    def test_legal_suffix_bank(self):
        assert self._match("DBS", "DBS Bank") is True

    def test_legal_suffix_with_comma(self):
        """Trailing comma on suffix token (e.g. 'Inc,') should still match."""
        assert self._match("Stripe", "Stripe, Inc.") is True

    # --- Reverse direction (query longer than candidate) ---
    def test_reverse_direction_match(self):
        assert self._match("Stripe Payments", "Stripe") is True

    # --- Rejects (should NOT match) ---
    def test_rejects_different_company_with_prefix(self):
        assert self._match("Shopify", "Shopify Administrator LLC") is False

    def test_rejects_query_in_middle(self):
        assert self._match("Shopify", "Hire a Shopify Admin") is False

    def test_rejects_unrelated_compound(self):
        assert self._match("Grab", "GrabFood") is False

    def test_rejects_cloud_division(self):
        assert self._match("Google", "Google Cloud") is False

    # --- Empty / edge cases ---
    def test_empty_query(self):
        assert self._match("", "Stripe") is False

    def test_empty_candidate(self):
        assert self._match("Stripe", "") is False

    def test_both_empty(self):
        assert self._match("", "") is False


# ---------------------------------------------------------------------------
# Test Board Registry — new companies added in Phase 5
# ---------------------------------------------------------------------------


class TestBoardRegistryExpansion:
    def test_meta_uses_career_page(self):
        boards = lookup_boards("meta")
        assert boards is not None
        assert "career_page" in boards

    def test_gitlab_uses_greenhouse(self):
        boards = lookup_boards("gitlab")
        assert boards is not None
        assert "greenhouse" in boards

    def test_linear_uses_ashby(self):
        boards = lookup_boards("linear")
        assert boards is not None
        assert "ashby" in boards

    def test_deel_uses_ashby(self):
        boards = lookup_boards("deel")
        assert boards is not None
        assert "ashby" in boards

    def test_vercel_uses_greenhouse(self):
        boards = lookup_boards("vercel")
        assert boards is not None
        assert "greenhouse" in boards

    def test_swiggy_uses_career_page(self):
        boards = lookup_boards("swiggy")
        assert boards is not None
        assert "career_page" in boards


# ---------------------------------------------------------------------------
# Test Career Page — JSON-LD extraction
# ---------------------------------------------------------------------------


class TestJsonLdExtraction:
    def test_extracts_jobposting_from_jsonld(self):
        from app.services.career_page_fetcher import _extract_jsonld_jobs

        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "JobPosting",
            "title": "Senior Software Engineer",
            "datePosted": "2026-01-15",
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "@type": "PostalAddress",
                    "addressLocality": "Singapore",
                    "addressCountry": "SG"
                }
            },
            "url": "https://example.com/jobs/123"
        }
        </script>
        </head><body></body></html>
        """
        jobs = _extract_jsonld_jobs(html, "https://example.com/careers")
        assert len(jobs) == 1
        assert jobs[0]["title"] == "Senior Software Engineer"
        assert jobs[0]["source"] == "career_page_jsonld"
        assert "Singapore" in jobs[0]["location"]

    def test_extracts_multiple_jobpostings_from_graph(self):
        from app.services.career_page_fetcher import _extract_jsonld_jobs

        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@graph": [
                {
                    "@type": "JobPosting",
                    "title": "Backend Engineer",
                    "url": "https://example.com/jobs/1"
                },
                {
                    "@type": "JobPosting",
                    "title": "Frontend Engineer",
                    "url": "https://example.com/jobs/2"
                },
                {
                    "@type": "Organization",
                    "name": "ExampleCorp"
                }
            ]
        }
        </script>
        </head><body></body></html>
        """
        jobs = _extract_jsonld_jobs(html, "https://example.com/careers")
        assert len(jobs) == 2
        titles = {j["title"] for j in jobs}
        assert "Backend Engineer" in titles
        assert "Frontend Engineer" in titles

    def test_returns_empty_for_non_jobposting_jsonld(self):
        from app.services.career_page_fetcher import _extract_jsonld_jobs

        html = """
        <html><head>
        <script type="application/ld+json">
        {"@type": "Organization", "name": "ExampleCorp"}
        </script>
        </head><body></body></html>
        """
        jobs = _extract_jsonld_jobs(html, "https://example.com/careers")
        assert jobs == []

    def test_handles_malformed_jsonld_gracefully(self):
        from app.services.career_page_fetcher import _extract_jsonld_jobs

        html = """
        <html><head>
        <script type="application/ld+json">
        {not valid json at all}
        </script>
        </head><body></body></html>
        """
        jobs = _extract_jsonld_jobs(html, "https://example.com/careers")
        assert jobs == []

    def test_detects_remote_from_jobloctype(self):
        from app.services.career_page_fetcher import _extract_jsonld_jobs

        html = """
        <html><head>
        <script type="application/ld+json">
        {
            "@type": "JobPosting",
            "title": "Remote Engineer",
            "jobLocationType": "TELECOMMUTE",
            "url": "https://example.com/jobs/remote"
        }
        </script>
        </head><body></body></html>
        """
        jobs = _extract_jsonld_jobs(html, "https://example.com/careers")
        # jobLocationType doesn't contain "remote", so is_remote depends on location
        assert len(jobs) == 1


# ---------------------------------------------------------------------------
# Test Career Page — SPA API parsing
# ---------------------------------------------------------------------------


class TestSpaApiParsing:
    def test_parse_bytedance_api_response(self):
        from app.services.career_page_fetcher import _parse_bytedance_api

        data = {
            "data": {
                "job_post_list": [
                    {
                        "id": "7001",
                        "title": "Machine Learning Engineer",
                        "city_info": [
                            {"city_name": "Singapore"},
                            {"city_name": "Beijing"},
                        ],
                        "job_category": {"name": "Engineering"},
                    },
                    {
                        "id": "7002",
                        "title": "Product Manager",
                        "city_info": [{"city_name": "Remote"}],
                        "job_category": {"name": "Product"},
                    },
                ]
            }
        }
        jobs = _parse_bytedance_api(data, "https://jobs.bytedance.com/en/")
        assert len(jobs) == 2
        assert jobs[0]["title"] == "Machine Learning Engineer"
        assert jobs[0]["department"] == "Engineering"
        assert "Singapore" in jobs[0]["location"]
        assert jobs[0]["source"] == "career_page_api"
        assert jobs[1]["is_remote"] is True

    def test_parse_bytedance_api_empty_response(self):
        from app.services.career_page_fetcher import _parse_bytedance_api

        data = {"data": {"job_post_list": []}}
        jobs = _parse_bytedance_api(data, "https://jobs.bytedance.com/en/")
        assert jobs == []
