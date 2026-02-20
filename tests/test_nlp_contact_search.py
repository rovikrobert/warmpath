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
