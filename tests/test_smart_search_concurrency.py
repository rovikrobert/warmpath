"""Concurrency test for smart_search bounded fetch.

Asserts that per-company `fetch_jobs_for_company` calls run concurrently
(under a Semaphore bound) instead of sequentially.
"""

from __future__ import annotations

import asyncio
import time
import uuid as uuid_mod
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.contact import Contact
from tests.conftest import TestSessionLocal, create_test_user_in_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    async with TestSessionLocal() as db:
        _, headers = await create_test_user_in_db(
            db, email="conc@test.com", full_name="Concurrency Tester"
        )
    return headers


@pytest_asyncio.fixture
async def user_id(auth_headers: dict, client: AsyncClient) -> str:
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    return resp.json()["data"]["id"]


@pytest_asyncio.fixture
async def four_companies_contacts(user_id: str) -> None:
    """A contact at each of four target companies so the smart search has work."""
    uid = uuid_mod.UUID(user_id)
    async with TestSessionLocal() as db:
        for company in ("CompanyA", "CompanyB", "CompanyC", "CompanyD"):
            db.add(
                Contact(
                    user_id=uid,
                    full_name=f"Person {company}",
                    first_name="Person",
                    last_name=company,
                    current_company=company,
                    current_title="Software Engineer",
                )
            )
        await db.commit()


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_smart_search_runs_per_company_fetches_concurrently(
    client: AsyncClient,
    auth_headers: dict,
    four_companies_contacts: None,
) -> None:
    """4 companies × 200ms fetch should finish in ~200ms (concurrent), not ~800ms."""
    await client.put(
        "/api/v1/preferences/job",
        headers=auth_headers,
        json={"target_role": "Software Engineer"},
    )

    fetch_delay = 0.2  # 200 ms per company
    n_companies = 4
    sequential_baseline = fetch_delay * n_companies  # ~0.8 s

    async def slow_fetch(name, boards, location_hint=None):
        await asyncio.sleep(fetch_delay)
        return [
            {
                "title": "Engineer",
                "url": f"https://example.com/{name}",
                "department": "eng",
                "location": "Remote",
                "is_remote": True,
                "source": "test",
            }
        ]

    # Patch lookup_or_discover_boards too — otherwise it makes outbound HEAD
    # probes per company in the sequential Phase 1, which would dominate the
    # measurement and mask the concurrency we're trying to verify.
    async def _fast_boards(name, db):
        return None, False

    with (
        patch("app.api.search.JobFetcher") as MockFetcherClass,
        patch("app.api.search.lookup_or_discover_boards", _fast_boards),
    ):
        mock_fetcher = MockFetcherClass.return_value
        mock_fetcher.fetch_jobs_for_company = AsyncMock(side_effect=slow_fetch)
        mock_fetcher.match_jobs_to_role = AsyncMock(
            side_effect=lambda jobs, role, sen=None, company_name="": jobs
        )
        mock_fetcher.filter_and_rank_jobs = MagicMock(
            side_effect=lambda jobs, role, **kw: [
                {**j, "fit_score": 50, "role_relevance": 50} for j in jobs
            ]
        )

        start = time.monotonic()
        resp = await client.post(
            "/api/v1/search/smart",
            headers=auth_headers,
            json={
                "company_names": ["CompanyA", "CompanyB", "CompanyC", "CompanyD"],
            },
        )
        elapsed = time.monotonic() - start

    assert resp.status_code == 201, resp.text
    # With Semaphore(4) (default SMART_SEARCH_FETCH_CONCURRENCY) all four
    # fetches should overlap. Allow generous slack for the rest of the
    # request pipeline; we just need to be substantially under the
    # sequential baseline.
    assert elapsed < sequential_baseline * 0.7, (
        f"smart_search should fan fetches out concurrently — "
        f"elapsed={elapsed:.3f}s, sequential baseline≈{sequential_baseline:.3f}s"
    )
    print(
        f"\n[BENCH] smart_search 4 companies (fetch=200ms each): "
        f"elapsed={elapsed * 1000:.0f}ms (sequential baseline≈{sequential_baseline * 1000:.0f}ms)"
    )
