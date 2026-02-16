import io
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.services.ai_matcher import (
    _mock_sco[RESEND_KEY_REDACTED],
    _mock_cultural_context,
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
        "target_role": None,
        "target_seniority": None,
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


async def _signup_and_get_token(
    client: AsyncClient, email: str = "search@example.com"
) -> str:
    resp = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": "secret123", "full_name": "Search User"},
    )
    return resp.json()["data"]["access_token"]


def _csv_file(content: str):
    return {
        "file": ("connections.csv", io.BytesIO(content.encode("utf-8")), "text/csv")
    }


# ---------------------------------------------------------------------------
# Unit tests — mock scoring (referral-focused)
# ---------------------------------------------------------------------------


class TestMockScoringReferral:
    """Tests for the new referral-focused mock scorer."""

    def test_company_match_primary_signal(self):
        """Working at a target company is the strongest signal (+50)."""
        search = _search(
            target_companies=["Stripe"],
            target_role="Software Engineer",
        )
        contact = _contact(current_company="Stripe", current_title="Designer")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score == 50.0
        assert "target company" in results[0].reasoning.lower()

    def test_company_plus_same_dept(self):
        """Company match + same department = high score."""
        search = _search(
            target_companies=["Stripe"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Stripe",
            current_title="Senior Software Engineer",
            location="San Francisco, CA",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        # 50 company + 25 same dept + 5 senior IC = 80
        assert results[0].relevance_score == 80.0
        assert results[0].match_type == "direct"
        assert results[0].referral_likelihood == "high"

    def test_company_plus_same_dept_plus_vp(self):
        """Company + same dept + VP title = top score."""
        search = _search(
            target_companies=["Stripe"],
            target_titles=["VP Engineering"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Stripe",
            current_title="VP Engineering",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        # 50 company + 25 dept + 10 VP + 10 title = 95
        assert results[0].relevance_score == 95.0
        assert results[0].match_type == "direct"
        assert results[0].referral_likelihood == "high"

    def test_company_match_adjacent_dept(self):
        """Company match + adjacent department."""
        search = _search(
            target_companies=["Stripe"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Stripe",
            current_title="Product Manager",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        # 50 company + 15 adjacent dept + 10 manager seniority = 75
        assert results[0].relevance_score == 75.0
        assert results[0].match_type == "adjacent"
        assert results[0].referral_likelihood == "high"

    def test_company_match_csuite_senior_advocate(self):
        """C-suite at target company = senior_advocate match type."""
        search = _search(
            target_companies=["Plaid"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Plaid",
            current_title="CTO",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        # 50 company + 5 C-suite = 55
        assert results[0].relevance_score == 55.0
        assert results[0].match_type == "senior_advocate"
        assert results[0].referral_likelihood == "medium"

    def test_no_company_match_low_score(self):
        """Without company match, score is very limited."""
        search = _search(
            target_companies=["Stripe"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Random Corp",
            current_title="Software Engineer",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score < 20.0

    def test_no_company_match_title_keyword(self):
        """Title keyword match without company gives small bonus."""
        search = _search(
            target_companies=["Stripe"],
            target_titles=["VP"],
            target_role="VP Engineering",
        )
        contact = _contact(
            current_company="Other Corp",
            current_title="VP of Sales",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        # 10 title + 0 everything else = 10
        assert results[0].relevance_score == 10.0

    def test_legacy_mode_no_company_targets(self):
        """Without target_companies, falls back to title+keyword scoring."""
        search = _search(target_titles=["CEO"])
        contact = _contact(current_title="CEO")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score == 40.0

    def test_legacy_keyword_match(self):
        search = _search(target_keywords=["fintech"])
        contact = _contact(current_company="Fintech Inc")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score == 15.0

    def test_legacy_location_match(self):
        search = _search(target_locations=["san francisco"])
        contact = _contact(location="San Francisco, CA")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score == 10.0

    def test_no_match_gets_base_score(self):
        search = _search(target_companies=["Stripe"], target_role="Engineer")
        contact = _contact(current_title="Analyst", current_company="Random")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].relevance_score == 5.0
        assert results[0].match_type == "alumni"
        assert results[0].referral_likelihood == "low"

    def test_empty_contacts(self):
        search = _search(target_companies=["Stripe"], target_role="Engineer")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [])
        assert results == []


# ---------------------------------------------------------------------------
# Cultural context tests
# ---------------------------------------------------------------------------


class TestCulturalContext:
    """Cultural context mock returns correct values for different regions."""

    def test_us_location_direct(self):
        ctx = _mock_cultural_context("San Francisco, CA", "Software Engineer")
        assert ctx["approach_style"] == "direct"
        assert ctx["recommended_channel"] == "linkedin_message"
        assert ctx["warm_up_suggested"] is False
        assert ctx["message_sequence"] == ["direct_ask"]
        assert "cultural_notes" in ctx
        assert len(ctx["cultural_notes"]) > 0

    def test_uk_location_direct(self):
        ctx = _mock_cultural_context("London, United Kingdom", "PM")
        assert ctx["approach_style"] == "direct"
        assert ctx["warm_up_suggested"] is False

    def test_japan_relationship_first(self):
        ctx = _mock_cultural_context("Tokyo, Japan", "Engineering Manager")
        assert ctx["approach_style"] == "relationship-first"
        assert ctx["warm_up_suggested"] is True
        assert ctx["message_sequence"] == ["reconnect", "explore", "ask"]

    def test_singapo[RESEND_KEY_REDACTED](self):
        ctx = _mock_cultural_context("Singapore", "Director")
        assert ctx["approach_style"] == "relationship-first"
        assert ctx["warm_up_suggested"] is True

    def test_china_relationship_first(self):
        ctx = _mock_cultural_context("Shanghai, China", "VP")
        assert ctx["approach_style"] == "relationship-first"
        assert ctx["warm_up_suggested"] is True

    def test_unknown_location_formal(self):
        ctx = _mock_cultural_context("", "Analyst")
        assert ctx["approach_style"] == "formal-indirect"
        assert ctx["warm_up_suggested"] is False
        assert ctx["message_sequence"] == ["reconnect", "ask"]

    def test_european_formal(self):
        """Non-UK European locations default to formal-indirect."""
        ctx = _mock_cultural_context("Berlin, Germany", "Engineer")
        assert ctx["approach_style"] == "formal-indirect"

    def test_all_fields_present(self):
        """Every cultural context has all required fields."""
        for loc in ["New York, NY", "Tokyo, Japan", "Berlin, Germany", ""]:
            ctx = _mock_cultural_context(loc, "Engineer")
            assert "approach_style" in ctx
            assert "recommended_channel" in ctx
            assert "cultural_notes" in ctx
            assert "warm_up_suggested" in ctx
            assert "message_sequence" in ctx
            assert isinstance(ctx["message_sequence"], list)
            assert len(ctx["message_sequence"]) >= 1


# ---------------------------------------------------------------------------
# Match type tests
# ---------------------------------------------------------------------------


class TestMatchTypes:
    """Match types are correctly assigned based on referral path."""

    def test_direct_same_dept_at_company(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Stripe", current_title="Software Engineer")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].match_type == "direct"

    def test_adjacent_dept_at_company(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Stripe", current_title="Data Scientist")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].match_type == "adjacent"

    def test_senior_advocate_csuite(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Stripe", current_title="CEO")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].match_type == "senior_advocate"

    def test_senior_advocate_vp_diff_dept(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Stripe", current_title="VP Sales")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].match_type == "senior_advocate"

    def test_alumni_low_score(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Random Corp", current_title="Analyst")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].match_type == "alumni"

    def test_four_valid_types(self):
        """All match types returned by mock are from the valid set."""
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contacts = [
            _contact(
                current_company="Stripe", current_title="Senior Software Engineer"
            ),
            _contact(current_company="Stripe", current_title="Product Manager"),
            _contact(current_company="Stripe", current_title="CEO"),
            _contact(current_company="Other", current_title="Analyst"),
        ]
        results = _mock_sco[RESEND_KEY_REDACTED](search, contacts)
        valid_types = {"direct", "adjacent", "senior_advocate", "alumni"}
        for r in results:
            assert r.match_type in valid_types


# ---------------------------------------------------------------------------
# Referral likelihood tests
# ---------------------------------------------------------------------------


class TestReferralLikelihood:
    def test_high_likelihood(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(
            current_company="Stripe",
            current_title="Senior Software Engineer",
            location="San Francisco, CA",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].referral_likelihood == "high"
        assert results[0].relevance_score >= 70

    def test_medium_likelihood(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Stripe", current_title="CEO")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].referral_likelihood == "medium"
        assert 45 <= results[0].relevance_score < 70

    def test_low_likelihood(self):
        search = _search(target_companies=["Stripe"], target_role="Software Engineer")
        contact = _contact(current_company="Random", current_title="Analyst")
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        assert results[0].referral_likelihood == "low"
        assert results[0].relevance_score < 45


# ---------------------------------------------------------------------------
# ContactMatch fields completeness
# ---------------------------------------------------------------------------


class TestContactMatchFields:
    """Every ContactMatch has all required fields populated."""

    def test_all_fields_present(self):
        search = _search(
            target_companies=["Stripe"],
            target_role="Software Engineer",
        )
        contact = _contact(
            current_company="Stripe",
            current_title="Senior Engineer",
            location="New York, NY",
        )
        results = _mock_sco[RESEND_KEY_REDACTED](search, [contact])
        m = results[0]
        assert m.contact_id is not None
        assert isinstance(m.relevance_score, float)
        assert isinstance(m.reasoning, str) and len(m.reasoning) > 0
        assert m.match_type in {"direct", "adjacent", "senior_advocate", "alumni"}
        assert m.referral_likelihood in {"high", "medium", "low"}
        assert isinstance(m.cultural_context, dict)
        assert "approach_style" in m.cultural_context
        assert "cultural_notes" in m.cultural_context
        assert isinstance(m.recommended_channel, str)
        assert isinstance(m.message_sequence, list)


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
            "target_role": "VP Engineering",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["data"]["name"] == "Find VPs at Fintech"
    assert body["data"]["target_titles"] == ["VP"]
    assert body["data"]["target_companies"] == ["Fintech"]
    assert body["data"]["target_role"] == "VP Engineering"
    assert body["data"]["status"] == "active"


async def test_list_searches(client: AsyncClient):
    token = await _signup_and_get_token(client, email="list@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Search 1", "target_role": "Engineer"},
    )
    await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Search 2", "target_role": "Designer"},
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
        json={
            "name": "My Search",
            "description": "Find key contacts",
            "target_role": "Product Manager",
        },
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

    # Upload contacts
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
            "target_role": "VP Engineering",
        },
    )
    search_id = create_resp.json()["data"]["id"]

    # Run the search
    run_resp = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    assert run_resp.status_code == 200
    # Only Bob (VP at Fintech Inc) scores >= 20 with company match
    assert run_resp.json()["data"]["matches_found"] == 1


async def test_run_search_no_contacts(client: AsyncClient):
    token = await _signup_and_get_token(client, email="empty@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={"name": "Empty search", "target_role": "Engineer"},
    )
    search_id = create_resp.json()["data"]["id"]

    run_resp = await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    assert run_resp.status_code == 200
    assert run_resp.json()["data"]["matches_found"] == 0


async def test_search_results_sorted_by_combined_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="sorted@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Find VPs at Fintech",
            "target_titles": ["VP"],
            "target_companies": ["Fintech"],
            "target_role": "VP Engineering",
        },
    )
    search_id = create_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 1

    # Bob (VP of Engineering at Fintech Inc): 50 company + 25 dept + 10 VP + 10 title = 95
    assert body["data"][0]["contact_name"] == "Bob Jones"
    assert body["data"][0]["relevance_score"] == 95.0


async def test_search_results_include_contact_info(client: AsyncClient):
    token = await _signup_and_get_token(client, email="info@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Find CEOs at Acme",
            "target_titles": ["CEO"],
            "target_companies": ["Acme"],
            "target_role": "CEO",
        },
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
    # New referral fields
    assert "referral_likelihood" in first
    assert "cultural_context" in first
    assert "recommended_channel" in first
    assert "message_sequence" in first


async def test_search_results_include_warm_score(client: AsyncClient):
    token = await _signup_and_get_token(client, email="warm@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Check warm",
            "target_titles": ["CEO"],
            "target_companies": ["Acme"],
            "target_role": "CEO",
        },
    )
    search_id = create_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    for result in resp.json()["data"]:
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
        json={
            "name": "Rerun test",
            "target_titles": ["CEO"],
            "target_companies": ["Acme"],
            "target_role": "CEO",
        },
    )
    search_id = create_resp.json()["data"]["id"]

    # Run twice
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    resp1 = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    count1 = resp1.json()["meta"]["total"]

    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)
    resp2 = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    count2 = resp2.json()["meta"]["total"]

    # Upsert, not duplicate
    assert count1 == count2 == 1


async def test_search_user_scoped(client: AsyncClient):
    """User B should not see User A's searches."""
    token_a = await _signup_and_get_token(client, email="sa@example.com")
    headers_a = {"Authorization": f"Bearer {token_a}"}

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers_a,
        json={"name": "User A Search", "target_role": "Engineer"},
    )
    search_id = create_resp.json()["data"]["id"]

    token_b = await _signup_and_get_token(client, email="sb@example.com")
    headers_b = {"Authorization": f"Bearer {token_b}"}

    resp = await client.get(f"/api/v1/search/{search_id}", headers=headers_b)
    assert resp.status_code == 404

    resp = await client.get("/api/v1/search", headers=headers_b)
    assert resp.json()["meta"]["total"] == 0


async def test_search_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/api/v1/search", json={"name": "No auth", "target_role": "Engineer"}
    )
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


# ---------------------------------------------------------------------------
# Cultural context in API results
# ---------------------------------------------------------------------------


async def test_search_results_have_cultural_context(client: AsyncClient):
    """Search results include cultural context from the AI matcher."""
    token = await _signup_and_get_token(client, email="cultural@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    await client.post(
        "/api/v1/contacts/upload", headers=headers, files=_csv_file(SAMPLE_CSV)
    )

    create_resp = await client.post(
        "/api/v1/search",
        headers=headers,
        json={
            "name": "Cultural check",
            "target_titles": ["VP"],
            "target_companies": ["Fintech"],
            "target_role": "VP Engineering",
        },
    )
    search_id = create_resp.json()["data"]["id"]
    await client.post(f"/api/v1/search/{search_id}/run", headers=headers)

    resp = await client.get(f"/api/v1/search/{search_id}/results", headers=headers)
    results = resp.json()["data"]
    assert len(results) >= 1

    for r in results:
        ctx = r["cultural_context"]
        assert ctx is not None
        assert "approach_style" in ctx
        assert "recommended_channel" in ctx
        assert "cultural_notes" in ctx
        assert "warm_up_suggested" in ctx
        assert "message_sequence" in ctx
        assert "referral_likelihood" in ctx
        # Top-level convenience fields
        assert r["referral_likelihood"] in ("high", "medium", "low")
        assert r["recommended_channel"] is not None
        assert isinstance(r["message_sequence"], list)
