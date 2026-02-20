"""Tests for NLP contact search query parser (mock mode)."""

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


def test_softwa[RESEND_KEY_REDACTED]():
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
