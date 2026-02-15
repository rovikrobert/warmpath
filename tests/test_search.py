import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.services.ai_matcher import (
    ContactMatch,
    _mock_score_contacts,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _Stub:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _search(**kwargs):
    defaults = {
        "target_titles": None,
        "target_companies": None,
        "target_industries": None,
        "target_locations": None,
        "target_keywords": None,
        "description": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


def _contact(**kwargs):
    import uuid

    defaults = {
        "id": uuid.uuid4(),
        "full_name": "Test User",
        "current_title": None,
        "current_company": None,
        "location": None,
    }
    defaults.update(kwargs)
    return _Stub(**defaults)


SAMPLE_CSV = (
    "First Name,Last Name,Email Address,Company,Position,Connected On\n"
    "Alice,Smith,alice@example.com,Acme Corp,CEO,{recent}\n"
    "Bob,Jones,bob@example.com,Fintech Inc,VP of Engineering,{recent2}\n"
    "Charlie,Brown,charlie@example.com,Other Co,Analyst,{old}\n"
).format(
    recent=(date.today() - timedelta(days=30)).strftime("%d %b %Y"),
    recent2=(date.today() - timedelta(days=60)).strftime("%d %b %Y"),
    old=(date.today() - timedelta(days=2000)).strftime("%d %b %Y"),
)


async def _signup_and_get_token(client: AsyncClient, email: str = "search@example.com") -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "Search User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str):
    return {"file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")}


# ---------------------------------------------------------------------------
# Unit tests — mock scoring
# ---------------------------------------------------------------------------


class TestMockScoring:
    def test_title_match(self):
        search = _search(target_titles=["CEO"])
        contact = _contact(current_title="CEO")
        results = _mock_score_contacts(search, [contact])
        assert len(results) == 1
        assert results[0].relevance_score == 40.0
        assert results[0].match_type == "indirect"  # 40 is indirect
        assert "Title matches" in results[0].reasoning

    def test_company_match(self):
        search = _search(target_companies=["Acme"])
        contact = _contact(current_company="Acme Corp")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 30.0
        assert "target company" in results[0].reasoning

    def test_location_match(self):
        search = _search(target_locations=["San Francisco"])
        contact = _contact(location="San Francisco, CA")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 15.0

    def test_keyword_match(self):
        search = _search(target_keywords=["fintech"])
        contact = _contact(current_company="Fintech Inc")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 15.0
        assert "keyword" in results[0].reasoning

    def test_full_match(self):
        """Title + company + location + keyword = 100 (capped)."""
        search = _search(
            target_titles=["ceo"],
            target_companies=["acme"],
            target_locations=["sf"],
            target_keywords=["sales"],
        )
        contact = _contact(
            current_title="CEO of Sales",
            current_company="Acme Corp",
            location="SF Bay Area",
        )
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 100.0
        assert results[0].match_type == "direct"

    def test_no_match_gets_base_score(self):
        search = _search(target_titles=["CEO"])
        contact = _contact(current_title="Analyst")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 5.0
        assert results[0].match_type == "weak"

    def test_multiple_contacts(self):
        search = _search(target_titles=["vp"])
        contacts = [
            _contact(current_title="VP of Sales"),
            _contact(current_title="Analyst"),
            _contact(current_title="VP Engineering"),
        ]
        results = _mock_score_contacts(search, contacts)
        assert len(results) == 3
        # Two VPs should match, one should not
        scores = [r.relevance_score for r in results]
        assert scores[0] == 40.0
        assert scores[1] == 5.0
        assert scores[2] == 40.0

    def test_case_insensitive_matching(self):
        search = _search(target_titles=["ceo"])
        contact = _contact(current_title="CEO")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 40.0

    def test_empty_contacts(self):
        search = _search(target_titles=["CEO"])
        results = _mock_score_contacts(search, [])
        assert results == []

    def test_no_criteria(self):
        search = _search()
        contact = _contact(current_title="CEO")
        results = _mock_score_contacts(search, [contact])
        assert results[0].relevance_score == 5.0


# ---------------------------------------------------------------------------
# Integration tests — API endpoints
# ---------------------------------------------------------------------------


async def test_create_search(client: AsyncClient):
    token = await _signup_and_get_token(client)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Find VPs at Fintech",
            "target_titles": ["VP"],
            "target_companies": ["Fintech"],
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["name"] == "Find VPs at Fintech"
    assert body["data"]["target_titles"] == ["VP"]
    assert body["data"]["target_companies"] == ["Fintech"]
    assert body["data"]["status"] == "active"


async def test_list_searches(client: AsyncClient):
    token = await _signup_and_get_token(client, email="list@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Create two searches
    await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Search 1"},
    )
    await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Search 2"},
    )

    resp = await client.get("/api/v1/search", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["meta"]["total"] == 2
    assert len(body["data"]) == 2


async def test_get_search(client: AsyncClient):
    token = await _signup_and_get_token(client, email="get@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "My Search", "description": "Find key contacts"},
    )
    search_id = create_resp.json()["data"]["id"]

    resp = await client.get(f"/api/v1/search/{search_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "My Search"
    assert resp.json()["data"]["description"] == "Find key contacts"


async def test_get_nonexistent_search(client: AsyncClient):
    token = await _signup_and_get_token(client, email="miss@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.get(
        "/api/v1/search/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


async def test_run_search_with_contacts(client: AsyncClient):
    token = await _signup_and_get_token(client, email="run@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload contacts first
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    # Create search targeting VPs at Fintech
    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "VP at Fintech",
            "target_titles": ["VP"],
            "target_companies": ["Fintech"],
        },
    )
    search_id = create_resp.json()["data"]["id"]

    # Run the search
    run_resp = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["matches_found"] == 3  # all 3 contacts scored


async def test_run_search_no_contacts(client: AsyncClient):
    token = await _signup_and_get_token(client, email="empty@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Empty search"},
    )
    search_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["matches_found"] == 0


async def test_search_results_sorted_by_combined_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="sorted@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Upload contacts
    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    # Search targeting VP at Fintech — Bob should score highest (title + company match)
    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Find VPs at Fintech",
            "target_titles": ["VP"],
            "target_companies": ["Fintech"],
        },
    )
    search_id = create_resp.json()["data"]["id"]

    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    # Get results
    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 3

    # Results should be sorted by combined_score descending
    combined_scores = [r["combined_score"] for r in body["data"]]
    assert combined_scores == sorted(combined_scores, reverse=True)

    # Bob (VP of Engineering at Fintech Inc) should be first
    assert body["data"][0]["contact_name"] == "Bob Jones"
    assert body["data"][0]["relevance_score"] == 70.0  # 40 title + 30 company


async def test_search_results_include_contact_info(client: AsyncClient):
    token = await _signup_and_get_token(client, email="info@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "All", "target_titles": ["CEO"]},
    )
    search_id = create_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    first = resp.json()["data"][0]

    assert "contact_name" in first
    assert "contact_title" in first
    assert "contact_company" in first
    assert "warm_score" in first
    assert "combined_score" in first
    assert "match_reasoning" in first
    assert "match_type" in first


async def test_search_results_include_warm_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="warm@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Check warm", "target_titles": ["CEO"]},
    )
    search_id = create_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    for result in resp.json()["data"]:
        # Warm scores should exist since upload auto-computes them
        assert result["warm_score"] is not None


async def test_rerun_search_updates_results(client: AsyncClient):
    token = await _signup_and_get_token(client, email="rerun@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Rerun test", "target_titles": ["CEO"]},
    )
    search_id = create_resp.json()["data"]["id"]

    # Run twice
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    resp1 = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    count1 = resp1.json()["meta"]["total"]

    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    resp2 = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    count2 = resp2.json()["meta"]["total"]

    # Should have same count (upsert, not duplicate)
    assert count1 == count2 == 3


async def test_search_user_scoped(client: AsyncClient):
    """User B should not see User A's searches."""
    token_a = await _signup_and_get_token(client, email="sa@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers_a,
        json={"name": "User A Search"},
    )
    search_id = create_resp.json()["data"]["id"]

    token_b = await _signup_and_get_token(client, email="sb@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # User B cannot see User A's search
    resp = await client.get(f"/api/v1/search/{search_id}", headers=headers_b)
    assert resp.status_code == 404

    # User B's list is empty
    resp = await client.get("/api/v1/search", headers=headers_b)
    assert resp.json()["meta"]["total"] == 0


async def test_search_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/search", json={"name": "No auth"})
    assert resp.status_code in (401, 403)

    resp = await client.get("/api/v1/search")
    assert resp.status_code in (401, 403)


async def test_run_nonexistent_search(client: AsyncClient):
    token = await _signup_and_get_token(client, email="norun@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/search/00000000-0000-0000-0000-000000000000/run", headers=headers
    )
    assert resp.status_code == 404
