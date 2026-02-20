"""Tests for NLP contact search query parser and scorer."""

from app.services.nlp_contact_search import parse_query_mock


# ---------------------------------------------------------------------------
# Company extraction
# ---------------------------------------------------------------------------


def test_big_tech_group_expands_to_six_companies():
    result = parse_query_mock("engineers at big tech")
    assert "Google" in result.companies
    assert "Meta" in result.companies
    assert "Apple" in result.companies
    assert "Amazon" in result.companies
    assert "Microsoft" in result.companies
    assert "Netflix" in result.companies
    assert len(result.companies) == 6


def test_faang_group_expands_to_five_companies():
    result = parse_query_mock("product managers from FAANG")
    assert "Google" in result.companies
    assert "Meta" in result.companies
    assert "Netflix" in result.companies
    assert len(result.companies) == 5
    # FAANG doesn't include Microsoft
    assert "Microsoft" not in result.companies


def test_specific_company_extracted_from_at_pattern():
    result = parse_query_mock("engineers at Stripe in San Francisco")
    assert "Stripe" in result.companies


def test_specific_company_extracted_from_from_pattern():
    result = parse_query_mock("people from Google")
    assert "Google" in result.companies


# ---------------------------------------------------------------------------
# Seniority extraction
# ---------------------------------------------------------------------------


def test_c_suite_seniority_detected_from_cto():
    result = parse_query_mock("CTOs at startups")
    assert "c_suite" in result.seniority


def test_multiple_seniority_levels_detected():
    result = parse_query_mock("senior directors and VPs in engineering")
    assert "senior" in result.seniority
    assert "director" in result.seniority
    assert "vp" in result.seniority


# ---------------------------------------------------------------------------
# Title extraction
# ---------------------------------------------------------------------------


def test_title_keywords_extracted_from_query():
    result = parse_query_mock("data scientists at Meta in Singapore")
    assert "data scientist" in result.titles


def test_software_engineer_title_extracted():
    result = parse_query_mock("software engineers at Google")
    assert "software engineer" in result.titles
    # "engineer" is a substring of "software engineer" — both should match
    assert "engineer" in result.titles


# ---------------------------------------------------------------------------
# Location extraction
# ---------------------------------------------------------------------------


def test_location_extracted_from_in_clause():
    result = parse_query_mock("engineers in Singapore")
    assert "Singapore" in result.locations


def test_location_alias_maps_to_canonical_name():
    result = parse_query_mock("designers in SF or NYC")
    assert "San Francisco" in result.locations
    assert "New York" in result.locations


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------


def test_former_colleague_relationship_type_detected():
    result = parse_query_mock("former colleagues at Google")
    assert "former_colleague" in result.relationship_types


def test_friend_relationship_type_detected():
    result = parse_query_mock("friends who work at Stripe")
    assert "friend" in result.relationship_types


# ---------------------------------------------------------------------------
# Combined / complex queries
# ---------------------------------------------------------------------------


def test_full_query_extracts_all_dimensions():
    result = parse_query_mock("CTOs from big tech in Singapore")
    assert "c_suite" in result.seniority
    assert "Google" in result.companies
    assert "Singapore" in result.locations
    assert result.raw_query == "CTOs from big tech in Singapore"


def test_empty_query_returns_empty_parsed_query():
    result = parse_query_mock("")
    assert result.titles == []
    assert result.companies == []
    assert result.seniority == []
    assert result.locations == []
    assert result.relationship_types == []
    assert result.raw_query == ""


def test_unparseable_query_returns_empty_lists_gracefully():
    result = parse_query_mock("asdfghjkl random nonsense 12345")
    assert result.titles == []
    assert result.companies == []
    assert result.seniority == []
    assert result.locations == []
    assert result.relationship_types == []
    assert result.raw_query == "asdfghjkl random nonsense 12345"


# ---------------------------------------------------------------------------
# Contact scorer — score_contact()
# ---------------------------------------------------------------------------

from app.services.nlp_contact_search import ParsedQuery, score_contact  # noqa: E402


def test_exact_company_match_scores_high():
    parsed = ParsedQuery(companies=["Google"], raw_query="people at Google")
    score = score_contact(parsed, "Google", None, None, None, company_matched=True)
    assert score >= 30


def test_title_keyword_match():
    parsed = ParsedQuery(titles=["engineer"], raw_query="engineers")
    score = score_contact(
        parsed, None, "Software Engineer", None, None, company_matched=False
    )
    assert score >= 28


def test_location_match():
    parsed = ParsedQuery(locations=["Singapore"], raw_query="people in Singapore")
    score = score_contact(parsed, None, None, "Singapore", None, company_matched=False)
    assert score >= 20


def test_relationship_type_match():
    parsed = ParsedQuery(
        relationship_types=["former_colleague"], raw_query="former colleagues"
    )
    score = score_contact(
        parsed, None, None, None, "former_colleague", company_matched=False
    )
    assert score >= 10


def test_no_match_scores_below_threshold():
    parsed = ParsedQuery(
        titles=["engineer"],
        companies=["Google"],
        locations=["Singapore"],
        raw_query="engineers at Google in Singapore",
    )
    score = score_contact(
        parsed, "Acme Corp", "Accountant", "London", None, company_matched=False
    )
    assert score < 20


def test_compound_match_scores_high():
    parsed = ParsedQuery(
        titles=["engineer"],
        companies=["Google"],
        locations=["Singapore"],
        relationship_types=["former_colleague"],
        raw_query="former colleague engineers at Google in Singapore",
    )
    score = score_contact(
        parsed,
        "Google",
        "Software Engineer",
        "Singapore",
        "former_colleague",
        company_matched=True,
    )
    assert score >= 80


def test_seniority_match_boosts_title_score():
    parsed = ParsedQuery(
        seniority=["director"],
        companies=["Google"],
        raw_query="directors at Google",
    )
    score = score_contact(
        parsed, "Google", "Director of Engineering", None, None, company_matched=True
    )
    assert score >= 35


# ---------------------------------------------------------------------------
# Real Claude API parser — parse_query_real() with mocked API
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch  # noqa: E402

from app.services.nlp_contact_search import parse_query_real  # noqa: E402


def test_parse_query_real_returns_parsed_query():
    mock_response = MagicMock()
    mock_response.content = [
        MagicMock(
            text='{"titles": ["engineer"], "companies": ["Google"], '
            '"seniority": ["senior"], "locations": ["Singapore"], '
            '"relationship_types": []}'
        )
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = parse_query_real("senior engineers at Google in Singapore")

    assert "engineer" in result.titles
    assert "Google" in result.companies
    assert "senior" in result.seniority
    assert "Singapore" in result.locations
    assert result.raw_query == "senior engineers at Google in Singapore"


def test_parse_query_real_falls_back_to_mock_on_error():
    with patch("anthropic.Anthropic", side_effect=RuntimeError("API unavailable")):
        result = parse_query_real("engineers at Google")

    # Should fall back to mock parser, which still extracts "Google"
    assert "Google" in result.companies
    assert result.raw_query == "engineers at Google"


# ---------------------------------------------------------------------------
# Integration tests — POST /contacts/nlp-search endpoint
# ---------------------------------------------------------------------------

import uuid  # noqa: E402

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.main import app as _app  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.contact import Contact  # noqa: E402
from tests.conftest import (  # noqa: E402
    TestSessionLocal,
    create_test_user_in_db,
)

NLP_SEARCH_URL = "/api/v1/contacts/nlp-search"


@pytest_asyncio.fixture
async def nlp_client() -> AsyncClient:  # type: ignore[misc]
    transport = ASGITransport(app=_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def nlp_auth_headers():
    """Create a test user and return auth headers."""
    async with TestSessionLocal() as db:
        user, headers = await create_test_user_in_db(
            db, email="nlp-test@example.com", full_name="NLP Test User"
        )
    return headers


@pytest_asyncio.fixture
async def nlp_user_id(nlp_client: AsyncClient, nlp_auth_headers: dict) -> uuid.UUID:
    """Get user ID from /auth/me."""
    resp = await nlp_client.get("/api/v1/auth/me", headers=nlp_auth_headers)
    assert resp.status_code == 200
    return uuid.UUID(resp.json()["data"]["id"])


@pytest_asyncio.fixture
async def nlp_contacts(nlp_user_id: uuid.UUID):
    """Seed 4 contacts with company_id set, plus Company rows."""
    async with TestSessionLocal() as db:
        # Create companies
        google = Company(id=uuid.uuid4(), name="Google")
        meta = Company(id=uuid.uuid4(), name="Meta")
        stripe = Company(id=uuid.uuid4(), name="Stripe")
        db.add_all([google, meta, stripe])
        await db.flush()

        # Create contacts
        alice = Contact(
            user_id=nlp_user_id,
            first_name="Alice",
            last_name="Chen",
            full_name="Alice Chen",
            current_title="CTO",
            current_company="Google",
            company_id=google.id,
            location="Singapore",
            relationship_type="former_colleague",
            source="manual",
        )
        bob = Contact(
            user_id=nlp_user_id,
            first_name="Bob",
            last_name="Smith",
            full_name="Bob Smith",
            current_title="Senior Software Engineer",
            current_company="Meta",
            company_id=meta.id,
            location="San Francisco",
            source="manual",
        )
        carol = Contact(
            user_id=nlp_user_id,
            first_name="Carol",
            last_name="Jones",
            full_name="Carol Jones",
            current_title="Product Manager",
            current_company="Stripe",
            company_id=stripe.id,
            location="New York",
            relationship_type="alumni",
            source="manual",
        )
        dave = Contact(
            user_id=nlp_user_id,
            first_name="Dave",
            last_name="Wilson",
            full_name="Dave Wilson",
            current_title="VP of Engineering",
            current_company="Google",
            company_id=google.id,
            location="Singapore",
            source="manual",
        )
        db.add_all([alice, bob, carol, dave])
        await db.commit()

    return [alice, bob, carol, dave]


@pytest.mark.asyncio
async def test_nlp_search_returns_ranked_results(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list
):
    """'CTOs at Google' finds Alice (CTO at Google) ranked first."""
    resp = await nlp_client.post(
        NLP_SEARCH_URL, json={"query": "CTOs at Google"}, headers=nlp_auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    # Alice should be the top result (CTO at Google)
    top = body["data"][0]
    assert "Alice" in top["full_name"]
    assert body["meta"]["total_matched"] >= 1


@pytest.mark.asyncio
async def test_nlp_search_big_tech_query(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list
):
    """'engineers at big tech' finds Bob (Senior SWE at Meta)."""
    resp = await nlp_client.post(
        NLP_SEARCH_URL,
        json={"query": "engineers at big tech"},
        headers=nlp_auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    names = [d["full_name"] for d in body["data"]]
    assert any("Bob" in n for n in names)


@pytest.mark.asyncio
async def test_nlp_search_empty_query_returns_all(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list
):
    """Empty query returns all 4 contacts without scoring."""
    resp = await nlp_client.post(
        NLP_SEARCH_URL, json={"query": ""}, headers=nlp_auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) == 4
    assert body["meta"]["total_scanned"] == 4
    assert body["meta"]["total_matched"] == 4


@pytest.mark.asyncio
async def test_nlp_search_requires_auth(nlp_client: AsyncClient):
    """No auth header returns 401."""
    resp = await nlp_client.post(NLP_SEARCH_URL, json={"query": "engineers"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_nlp_search_location_filter(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list
):
    """'people in Singapore' finds Alice + Dave (both in Singapore)."""
    resp = await nlp_client.post(
        NLP_SEARCH_URL,
        json={"query": "people in Singapore"},
        headers=nlp_auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    names = [d["full_name"] for d in body["data"]]
    assert any("Alice" in n for n in names)
    assert any("Dave" in n for n in names)
    assert body["meta"]["interpretation"]["locations"] == ["Singapore"]


@pytest.mark.asyncio
async def test_nlp_search_response_includes_match_score(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list
):
    """Response items have an nlp_match_score field."""
    resp = await nlp_client.post(
        NLP_SEARCH_URL, json={"query": "CTOs at Google"}, headers=nlp_auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]) >= 1
    for item in body["data"]:
        assert "nlp_match_score" in item
        assert isinstance(item["nlp_match_score"], (int, float))


# ---------------------------------------------------------------------------
# Usage metering
# ---------------------------------------------------------------------------


class TestNlpSearchMetering:
    """NLP search is metered with free tier limits."""

    def test_nlp_search_route_is_metered(self):
        from app.middleware.usage_logger import match_metered_action

        action = match_metered_action("POST", "/api/v1/contacts/nlp-search")
        assert action == "nlp_search"

    def test_nlp_search_standard_free_tier_limit_is_ten(self):
        from app.middleware.usage_logger import _STANDARD_FREE_TIER_LIMITS

        assert _STANDARD_FREE_TIER_LIMITS["nlp_search"] == 10

    def test_nlp_search_beta_free_tier_limit_is_fifty(self):
        from app.middleware.usage_logger import _BETA_FREE_TIER_LIMITS

        assert _BETA_FREE_TIER_LIMITS["nlp_search"] == 50


# ---------------------------------------------------------------------------
# Bug regression tests: precision issues
# ---------------------------------------------------------------------------


class TestNlpParsePrecision:
    """Regression tests for parser precision bugs."""

    def test_cios_ctos_extracts_specific_titles_not_just_c_suite(self):
        """'CIOs/CTOs' should extract CIO and CTO as specific titles."""
        result = parse_query_mock("strictly CIOs/CTOs in the US")
        title_lower = [t.lower() for t in result.titles]
        assert "cio" in title_lower or "cios" in title_lower
        assert "cto" in title_lower or "ctos" in title_lower

    def test_cios_does_not_false_positive_ios_title(self):
        """'CIOs' should NOT match the 'ios' title keyword."""
        result = parse_query_mock("CIOs at Google")
        title_lower = [t.lower() for t in result.titles]
        assert "ios" not in title_lower

    def test_us_location_detected(self):
        """'in the US' should extract United States as a location."""
        result = parse_query_mock("CTOs in the US")
        assert len(result.locations) >= 1
        loc_lower = [loc.lower() for loc in result.locations]
        assert any("united states" in loc or "us" in loc for loc in loc_lower)

    def test_usa_location_detected(self):
        """'in the USA' should extract United States as a location."""
        result = parse_query_mock("engineers in the USA")
        assert len(result.locations) >= 1

    def test_specific_csuite_titles_score_higher_than_generic(self):
        """When user asks for CTO, a CTO should score higher than a CFO."""
        from app.services.nlp_contact_search import ParsedQuery, score_contact

        parsed = ParsedQuery(titles=["CTO"], seniority=["c_suite"])
        cto_score = score_contact(
            parsed,
            company_name=None,
            title="CTO",
            location=None,
            relationship_type=None,
            company_matched=False,
        )
        cfo_score = score_contact(
            parsed,
            company_name=None,
            title="CFO",
            location=None,
            relationship_type=None,
            company_matched=False,
        )
        assert cto_score > cfo_score

    def test_location_filters_out_wrong_country(self):
        """When user asks 'in the US', someone in Singapore should score 0 for location."""
        from app.services.nlp_contact_search import ParsedQuery, _score_location

        parsed = ParsedQuery(locations=["United States"])
        assert _score_location(parsed, "Singapore") == 0.0
        assert _score_location(parsed, "San Francisco, CA") > 0.0


# ---------------------------------------------------------------------------
# Service function: search_user_contacts()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_user_contacts_returns_dict_shape(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list, nlp_user_id
):
    """search_user_contacts() returns expected dict keys."""
    from app.services.nlp_contact_search import search_user_contacts

    async with TestSessionLocal() as db:
        result = await search_user_contacts(nlp_user_id, "CTOs at Google", db)

    assert "results" in result
    assert "interpretation" in result
    assert "total_scanned" in result
    assert "total_matched" in result
    assert isinstance(result["results"], list)
    assert result["total_matched"] >= 1


@pytest.mark.asyncio
async def test_search_user_contacts_result_fields(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list, nlp_user_id
):
    """Each result has full_name, current_company, current_title, warm_score, nlp_match_score."""
    from app.services.nlp_contact_search import search_user_contacts

    async with TestSessionLocal() as db:
        result = await search_user_contacts(nlp_user_id, "engineers at Google", db)

    for r in result["results"]:
        assert "full_name" in r
        assert "current_company" in r
        assert "current_title" in r
        assert "warm_score" in r
        assert "nlp_match_score" in r
        assert "relationship_type" in r
        assert "location" in r


@pytest.mark.asyncio
async def test_search_user_contacts_respects_limit(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list, nlp_user_id
):
    """Limit parameter caps the number of results."""
    from app.services.nlp_contact_search import search_user_contacts

    async with TestSessionLocal() as db:
        result = await search_user_contacts(nlp_user_id, "", db, limit=2)

    assert len(result["results"]) <= 2


@pytest.mark.asyncio
async def test_search_user_contacts_empty_query_returns_all(
    nlp_client: AsyncClient, nlp_auth_headers: dict, nlp_contacts: list, nlp_user_id
):
    """Empty query returns all contacts."""
    from app.services.nlp_contact_search import search_user_contacts

    async with TestSessionLocal() as db:
        result = await search_user_contacts(nlp_user_id, "", db)

    assert result["total_matched"] == 4
    assert len(result["results"]) == 4
