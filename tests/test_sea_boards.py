"""Tests for P15: SEA board registry expansion + career page fallback."""

import re
from unittest.mock import AsyncMock, patch

import httpx
import pytest_asyncio
from httpx import AsyncClient

from app.services.board_registry import BOARD_REGISTRY, REGIONS, lookup_boards
from app.services.career_page_fetcher import (
    CAREER_PAGES,
    _extract_jobs_from_html,
    fetch_career_page,
    lookup_career_page,
)
from app.services.job_fetcher import JobFetcher


# ---------------------------------------------------------------------------
# Board registry — SEA/India/ANZ companies present
# ---------------------------------------------------------------------------


class TestSEABoardRegistry:
    def test_singapo[RESEND_KEY_REDACTED](self):
        sea_companies = [
            "grab", "sea-group", "shopee", "lazada", "gojek", "carousell",
            "foodpanda", "ninja-van", "patsnap", "endowus", "syfe", "aspire",
            "funding-societies", "carro",
        ]
        for company in sea_companies:
            assert company in BOARD_REGISTRY, f"{company} missing from registry"

    def test_india_companies_present(self):
        india_companies = ["razorpay", "zerodha", "cred", "meesho", "phonepe"]
        for company in india_companies:
            assert company in BOARD_REGISTRY, f"{company} missing from registry"

    def test_anz_companies_present(self):
        anz_companies = ["canva", "atlassian", "afterpay"]
        for company in anz_companies:
            assert company in BOARD_REGISTRY, f"{company} missing from registry"

    def test_total_company_count(self):
        assert len(BOARD_REGISTRY) >= 52

    def test_regions_cover_all_companies(self):
        all_in_regions = set()
        for companies in REGIONS.values():
            all_in_regions.update(companies)
        for key in BOARD_REGISTRY:
            assert key in all_in_regions, f"{key} not in any REGIONS group"

    def test_lookup_grab(self):
        boards = lookup_boards("grab")
        assert boards is not None
        assert "greenhouse" in boards

    def test_lookup_razorpay(self):
        boards = lookup_boards("razorpay")
        assert boards is not None
        assert "greenhouse" in boards

    def test_lookup_canva(self):
        boards = lookup_boards("canva")
        assert boards is not None
        assert "greenhouse" in boards

    def test_all_entries_have_valid_source(self):
        valid_sources = {"greenhouse", "lever"}
        for name, entry in BOARD_REGISTRY.items():
            for source in entry:
                assert source in valid_sources, (
                    f"{name} has invalid source '{source}'"
                )


# ---------------------------------------------------------------------------
# Career page fetcher — unit tests
# ---------------------------------------------------------------------------


class TestCareerPageLookup:
    def test_known_company(self):
        url = lookup_career_page("grab")
        assert url is not None
        assert "grab" in url.lower() or "careers" in url.lower()

    def test_unknown_company(self):
        assert lookup_career_page("totally_unknown_xyz") is None

    def test_case_insensitive(self):
        url = lookup_career_page("Grab")
        # lookup_career_page lowercases the key
        assert url is not None

    def test_all_sea_companies_have_career_pages(self):
        sea = REGIONS.get("Singapore / SEA", [])
        for company in sea:
            url = lookup_career_page(company)
            assert url is not None, f"{company} missing from CAREER_PAGES"


class TestCareerPageHTMLExtraction:
    def test_extracts_job_links(self):
        html = """
        <html><body>
        <a href="/jobs/senior-engineer/">Senior Software Engineer</a>
        <a href="/jobs/product-manager/">Product Manager</a>
        <a href="/about">About Us</a>
        </body></html>
        """
        jobs = _extract_jobs_from_html(html, "https://example.com/careers/")
        assert len(jobs) == 2
        titles = {j["title"] for j in jobs}
        assert "Senior Software Engineer" in titles
        assert "Product Manager" in titles

    def test_skips_non_job_links(self):
        html = """
        <html><body>
        <a href="/about">About</a>
        <a href="/blog/post">Blog Post</a>
        <a href="/contact">Contact</a>
        </body></html>
        """
        jobs = _extract_jobs_from_html(html, "https://example.com/careers/")
        assert len(jobs) == 0

    def test_skips_navigation_links(self):
        html = """
        <html><body>
        <a href="/jobs/apply/">Apply Now</a>
        <a href="/jobs/view/">View</a>
        <a href="/jobs/backend-engineer/">Backend Engineer</a>
        </body></html>
        """
        jobs = _extract_jobs_from_html(html, "https://example.com/")
        titles = {j["title"] for j in jobs}
        assert "Apply Now" not in titles
        assert "Backend Engineer" in titles

    def test_deduplicates_urls(self):
        html = """
        <html><body>
        <a href="/jobs/engineer/">Engineer</a>
        <a href="/jobs/engineer/">Engineer (duplicate)</a>
        </body></html>
        """
        jobs = _extract_jobs_from_html(html, "https://example.com/")
        assert len(jobs) == 1

    def test_resolves_relative_urls(self):
        html = '<a href="/positions/dev/">Developer</a>'
        jobs = _extract_jobs_from_html(html, "https://example.com/careers/")
        assert len(jobs) == 1
        assert jobs[0]["url"] == "https://example.com/positions/dev/"

    def test_source_is_career_page(self):
        html = '<a href="/jobs/test/">Test Role</a>'
        jobs = _extract_jobs_from_html(html, "https://example.com/")
        assert len(jobs) == 1
        assert jobs[0]["source"] == "career_page"


class TestFetchCareerPage:
    async def test_successful_fetch(self):
        html = """
        <html><body>
        <a href="/jobs/swe/">Software Engineer</a>
        <a href="/jobs/pm/">Product Manager</a>
        </body></html>
        """
        mock_resp = httpx.Response(
            status_code=200,
            text=html,
            request=httpx.Request("GET", "https://example.com/careers"),
        )
        with patch("app.services.career_page_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetch_career_page("https://example.com/careers")

        assert len(jobs) == 2

    async def test_http_error_returns_empty(self):
        with patch("app.services.career_page_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                side_effect=httpx.HTTPError("Connection failed")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetch_career_page("https://example.com/careers")

        assert jobs == []

    async def test_404_returns_empty(self):
        mock_resp = httpx.Response(
            status_code=404,
            request=httpx.Request("GET", "https://example.com/careers"),
        )
        with patch("app.services.career_page_fetcher.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            jobs = await fetch_career_page("https://example.com/careers")

        assert jobs == []


# ---------------------------------------------------------------------------
# JobFetcher fallback chain
# ---------------------------------------------------------------------------


class TestFallbackChain:
    async def test_uses_greenhouse_first(self):
        """When Greenhouse returns results, career page is not called."""
        fetcher = JobFetcher()
        with patch.object(
            fetcher,
            "fetch_greenhouse_jobs",
            return_value=[{"title": "SWE", "source": "greenhouse"}],
        ) as gh_mock, patch(
            "app.services.career_page_fetcher.fetch_career_page"
        ) as cp_mock:
            jobs = await fetcher.fetch_jobs_for_company(
                "stripe", {"greenhouse": "stripe"}
            )
            gh_mock.assert_called_once()
            cp_mock.assert_not_called()
            assert len(jobs) == 1
            assert jobs[0]["source"] == "greenhouse"

    async def test_falls_back_to_career_page(self):
        """When ATS returns nothing and career page exists, use it."""
        fetcher = JobFetcher()
        with patch.object(
            fetcher, "fetch_greenhouse_jobs", return_value=[]
        ), patch(
            "app.services.career_page_fetcher.lookup_career_page",
            return_value="https://example.com/careers",
        ), patch(
            "app.services.career_page_fetcher.fetch_career_page",
            return_value=[{"title": "Dev", "source": "career_page"}],
        ) as cp_mock:
            jobs = await fetcher.fetch_jobs_for_company(
                "grab", {"greenhouse": "grab"}
            )
            cp_mock.assert_called_once_with("https://example.com/careers")
            assert len(jobs) == 1
            assert jobs[0]["source"] == "career_page"

    async def test_no_boards_tries_career_page(self):
        """When no board_ids at all, try career page directly."""
        fetcher = JobFetcher()
        with patch(
            "app.services.career_page_fetcher.lookup_career_page",
            return_value="https://example.com/careers",
        ), patch(
            "app.services.career_page_fetcher.fetch_career_page",
            return_value=[{"title": "PM", "source": "career_page"}],
        ):
            jobs = await fetcher.fetch_jobs_for_company("newco", None)
            assert len(jobs) == 1

    async def test_no_boards_no_career_page_returns_empty(self):
        """When nothing is available, return empty list."""
        fetcher = JobFetcher()
        with patch(
            "app.services.career_page_fetcher.lookup_career_page", return_value=None
        ):
            jobs = await fetcher.fetch_jobs_for_company("unknown_co", None)
            assert jobs == []


# ---------------------------------------------------------------------------
# API endpoint — scan with fallback
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "sea_test@test.com",
            "password": "testpass123",
            "full_name": "SEA Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "sea_test@test.com", "password": "testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestScanAPIFallback:
    async def test_scan_sea_company_with_fallback(
        self, client: AsyncClient, auth_headers
    ):
        """Scanning a SEA company should work via career page fallback."""
        with patch.object(
            JobFetcher,
            "fetch_jobs_for_company",
            return_value=[
                {
                    "title": "Backend Engineer",
                    "department": "Engineering",
                    "location": "Singapore",
                    "url": "https://grab.careers/jobs/backend-engineer",
                    "source": "career_page",
                    "source_job_id": "https://grab.careers/jobs/backend-engineer",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                }
            ],
        ):
            resp = await client.get(
                "/api/v1/jobs/scan/grab", headers=auth_headers
            )
            assert resp.status_code == 200
            assert resp.json()["meta"]["openings_count"] == 1

    async def test_scan_truly_unknown_still_404(
        self, client: AsyncClient, auth_headers
    ):
        """A company in neither registry nor career pages returns 404."""
        resp = await client.get(
            "/api/v1/jobs/scan/totally_unknown_company_xyz_123",
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_scan_known_ats_company_still_works(
        self, client: AsyncClient, auth_headers
    ):
        """Existing ATS companies (e.g. stripe) still scan normally."""
        with patch.object(
            JobFetcher,
            "fetch_jobs_for_company",
            return_value=[
                {
                    "title": "Staff Engineer",
                    "department": "Eng",
                    "location": "SF",
                    "url": "https://boards.greenhouse.io/stripe/jobs/1",
                    "source": "greenhouse",
                    "source_job_id": "gh-001",
                    "posted_at": None,
                    "is_remote": False,
                    "raw_data": {},
                }
            ],
        ):
            resp = await client.get(
                "/api/v1/jobs/scan/stripe", headers=auth_headers
            )
            assert resp.status_code == 200
            assert resp.json()["meta"]["openings_count"] == 1
