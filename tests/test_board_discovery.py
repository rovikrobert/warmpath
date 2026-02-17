"""Tests for company ATS auto-discovery and job filtering/ranking."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest_asyncio
from httpx import AsyncClient

from app.services.board_registry import (
    BOARD_REGISTRY,
    _slug_candidates,
    discover_boards,
    lookup_or_discover_boards,
    register_board,
)
from app.services.job_fetcher import JobFetcher


# ---------------------------------------------------------------------------
# A1: Slug candidate generation
# ---------------------------------------------------------------------------


class TestSlugCandidates:
    def test_simple_name(self):
        slugs = _slug_candidates("Stripe")
        assert "stripe" in slugs

    def test_two_word_name(self):
        slugs = _slug_candidates("Ninja Van")
        assert "ninja-van" in slugs
        assert "ninjavan" in slugs

    def test_strips_common_suffixes(self):
        slugs = _slug_candidates("ByteDance Inc.")
        assert any("bytedance" in s for s in slugs)
        # "inc" should be stripped
        assert not any("inc" in s for s in slugs)

    def test_strips_pte_ltd(self):
        slugs = _slug_candidates("Grab Holdings Pte Ltd")
        # "pte" and "ltd" stripped
        assert not any("pte" in s for s in slugs)
        assert not any("ltd" in s for s in slugs)

    def test_multi_word_generates_first_word(self):
        # "Group" is stripped as a common suffix → "sea" is the only slug
        slugs = _slug_candidates("Sea Group")
        assert "sea" in slugs
        # Multi-word without suffix stripping should produce dashed + joined
        slugs2 = _slug_candidates("Ninja Van")
        assert "ninja-van" in slugs2
        assert "ninjavan" in slugs2

    def test_empty_name(self):
        assert _slug_candidates("") == []
        assert _slug_candidates("   ") == []

    def test_deduplicates(self):
        slugs = _slug_candidates("openai")
        # Single word → dashed and joined are the same; should not duplicate
        assert len(slugs) == len(set(slugs))

    def test_removes_non_alphanumeric(self):
        slugs = _slug_candidates("Scale.AI")
        assert any("scaleai" in s or "scale" in s for s in slugs)


# ---------------------------------------------------------------------------
# A2: ATS probe function
# ---------------------------------------------------------------------------


class TestDiscoverBoards:
    async def test_discovers_greenhouse(self):
        """Simulate Greenhouse returning 200 for a slug."""

        async def _fake_head(url, **kwargs):
            if "greenhouse" in url:
                return httpx.Response(200, request=httpx.Request("HEAD", url))
            return httpx.Response(404, request=httpx.Request("HEAD", url))

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=_fake_head)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await discover_boards("testcorp")

        assert result is not None
        assert "greenhouse" in result

    async def test_discovers_lever(self):
        """Simulate Lever returning 200 for a slug."""

        async def _fake_head(url, **kwargs):
            if "lever" in url:
                return httpx.Response(200, request=httpx.Request("HEAD", url))
            return httpx.Response(404, request=httpx.Request("HEAD", url))

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=_fake_head)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await discover_boards("testcorp")

        assert result is not None
        assert "lever" in result

    async def test_discovers_ashby(self):
        """Simulate Ashby returning 200 for a slug."""

        async def _fake_head(url, **kwargs):
            if "ashby" in url:
                return httpx.Response(200, request=httpx.Request("HEAD", url))
            return httpx.Response(404, request=httpx.Request("HEAD", url))

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=_fake_head)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await discover_boards("testcorp")

        assert result is not None
        assert "ashby" in result

    async def test_returns_none_when_all_404(self):
        """When all probes return 404, should return None."""

        async def _fake_head(url, **kwargs):
            return httpx.Response(404, request=httpx.Request("HEAD", url))

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=_fake_head)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await discover_boards("unknown_company_xyz")

        assert result is None

    async def test_handles_network_error(self):
        """Network errors should not crash — just return None."""

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=httpx.HTTPError("Timeout"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            result = await discover_boards("testcorp")

        assert result is None


# ---------------------------------------------------------------------------
# A3: Cache layer (lookup_or_discover_boards)
# ---------------------------------------------------------------------------


class TestLookupOrDiscoverBoards:
    async def test_returns_static_registry_first(self, client: AsyncClient):
        """Known companies should use the static registry, not probe."""
        from tests.conftest import TestSessionLocal

        async with TestSessionLocal() as db:
            boards, was_discovered = await lookup_or_discover_boards("stripe", db)

        assert boards is not None
        assert "greenhouse" in boards
        assert was_discovered is False

    async def test_caches_discovery_result(self, client: AsyncClient):
        """After discovery, result should be cached in EnrichmentCache."""
        from app.models.enrichment import EnrichmentCache
        from sqlalchemy import select
        from tests.conftest import TestSessionLocal

        async def _fake_head(url, **kwargs):
            if "greenhouse" in url:
                return httpx.Response(200, request=httpx.Request("HEAD", url))
            return httpx.Response(404, request=httpx.Request("HEAD", url))

        with patch("app.services.board_registry.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(side_effect=_fake_head)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            async with TestSessionLocal() as db:
                boards, was_discovered = await lookup_or_discover_boards(
                    "cache_test_corp", db
                )
                await db.commit()

                # Verify cache entry exists
                result = await db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.cache_key == "board_discovery:cache_test_corp"
                    )
                )
                cached = result.scalar_one_or_none()

        assert boards is not None
        assert was_discovered is True
        assert cached is not None
        assert cached.data["boards"] is not None

        # Clean up runtime registry
        BOARD_REGISTRY.pop("cache_test_corp", None)

    async def test_caches_none_result(self, client: AsyncClient):
        """Even when nothing is found, cache the None result."""
        from app.models.enrichment import EnrichmentCache
        from sqlalchemy import select
        from tests.conftest import TestSessionLocal

        with patch(
            "app.services.board_registry.discover_boards",
            return_value=None,
        ):
            async with TestSessionLocal() as db:
                boards, was_discovered = await lookup_or_discover_boards(
                    "nonexistent_corp_xyz", db
                )
                await db.commit()

                result = await db.execute(
                    select(EnrichmentCache).where(
                        EnrichmentCache.cache_key
                        == "board_discovery:nonexistent_corp_xyz"
                    )
                )
                cached = result.scalar_one_or_none()

        assert boards is None
        assert was_discovered is False
        assert cached is not None
        assert cached.data["boards"] is None


# ---------------------------------------------------------------------------
# B1: Job filtering and ranking
# ---------------------------------------------------------------------------


class TestFilterAndRankJobs:
    def _make_jobs(self):
        return [
            {
                "title": "Senior Software Engineer",
                "location": "San Francisco, CA",
                "is_remote": False,
                "role_relevance": 90,
                "source": "greenhouse",
            },
            {
                "title": "Junior Software Engineer",
                "location": "Singapore",
                "is_remote": False,
                "role_relevance": 70,
                "source": "greenhouse",
            },
            {
                "title": "Staff Software Engineer",
                "location": "Remote",
                "is_remote": True,
                "role_relevance": 85,
                "source": "greenhouse",
            },
            {
                "title": "Software Engineer Intern",
                "location": "New York",
                "is_remote": False,
                "role_relevance": 60,
                "source": "greenhouse",
            },
            {
                "title": "Software Engineer",
                "location": None,
                "is_remote": False,
                "role_relevance": 75,
                "source": "lever",
            },
        ]

    def test_no_filters(self):
        fetcher = JobFetcher()
        jobs = self._make_jobs()
        result = fetcher.filter_and_rank_jobs(jobs, "Software Engineer")
        # All jobs returned, sorted by fit_score
        assert len(result) == 5
        assert all("fit_score" in j for j in result)

    def test_location_filter(self):
        fetcher = JobFetcher()
        jobs = self._make_jobs()
        result = fetcher.filter_and_rank_jobs(
            jobs, "Software Engineer", target_locations=["Singapore"]
        )
        # Only Singapore + remote + unknown-location jobs should pass
        locations = [j.get("location") for j in result]
        for loc in locations:
            if loc is not None:
                assert "singapore" in loc.lower() or "remote" in loc.lower()

    def test_seniority_boost(self):
        fetcher = JobFetcher()
        jobs = self._make_jobs()
        result = fetcher.filter_and_rank_jobs(
            jobs, "Software Engineer", target_seniority="Senior"
        )
        # Senior job should get +30 boost and be ranked first
        assert "Senior" in result[0]["title"]

    def test_seniority_penalty(self):
        fetcher = JobFetcher()
        jobs = self._make_jobs()
        result = fetcher.filter_and_rank_jobs(
            jobs, "Software Engineer", target_seniority="Senior"
        )
        # Intern/Junior should be penalized (lower scores)
        intern_score = next(j["fit_score"] for j in result if "Intern" in j["title"])
        senior_score = next(j["fit_score"] for j in result if "Senior" in j["title"])
        assert senior_score > intern_score

    def test_remote_bonus(self):
        fetcher = JobFetcher()
        jobs = self._make_jobs()
        result = fetcher.filter_and_rank_jobs(
            jobs,
            "Software Engineer",
            target_locations=["San Francisco"],
            open_to_remote=True,
        )
        remote_job = next(j for j in result if j.get("is_remote"))
        assert remote_job["fit_score"] >= remote_job["role_relevance"]

    def test_empty_input(self):
        fetcher = JobFetcher()
        assert fetcher.filter_and_rank_jobs([], "Engineer") == []

    def test_location_filter_excludes_non_matching(self):
        fetcher = JobFetcher()
        jobs = [
            {
                "title": "Engineer",
                "location": "London, UK",
                "is_remote": False,
                "role_relevance": 80,
            },
        ]
        result = fetcher.filter_and_rank_jobs(
            jobs,
            "Engineer",
            target_locations=["Singapore"],
            open_to_remote=False,
        )
        # London should be filtered out when looking for Singapore and not open to remote
        assert len(result) == 0


# ---------------------------------------------------------------------------
# API: scan endpoint with discovery
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "email": "discovery_test@test.com",
            "password": "Testpass123",
            "full_name": "Discovery Tester",
        },
    )
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"email": "discovery_test@test.com", "password": "Testpass123"},
    )
    token = login_res.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestScanWithDiscovery:
    async def test_scan_discovers_unknown_company(
        self, client: AsyncClient, auth_headers
    ):
        """Scanning an unknown company should try auto-discovery."""
        with (
            patch(
                "app.api.jobs.lookup_or_discover_boards",
                return_value=({"greenhouse": "bytedance"}, True),
            ),
            patch.object(
                JobFetcher,
                "fetch_jobs_for_company",
                return_value=[
                    {
                        "title": "Software Engineer",
                        "department": "Engineering",
                        "location": "Singapore",
                        "url": "https://boards.greenhouse.io/bytedance/jobs/1",
                        "source": "greenhouse",
                        "source_job_id": "bd-001",
                        "posted_at": None,
                        "is_remote": False,
                        "raw_data": {},
                    }
                ],
            ),
        ):
            resp = await client.get(
                "/api/v1/jobs/scan/bytedance", headers=auth_headers
            )
            assert resp.status_code == 200
            assert resp.json()["meta"]["openings_count"] == 1

    async def test_scan_falls_back_to_404_when_nothing_found(
        self, client: AsyncClient, auth_headers
    ):
        """When discovery and career page both fail, return 404."""
        with (
            patch(
                "app.api.jobs.lookup_or_discover_boards",
                return_value=(None, False),
            ),
            patch(
                "app.api.jobs.lookup_career_page",
                return_value=None,
            ),
        ):
            resp = await client.get(
                "/api/v1/jobs/scan/totally_unknown_xyz", headers=auth_headers
            )
            assert resp.status_code == 404
