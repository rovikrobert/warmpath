"""NLP query parser and scorer for natural-language contact search.

Converts free-text queries like "CTOs from big tech in Singapore" into
structured ``ParsedQuery`` objects with extracted titles, companies,
seniority levels, locations, and relationship types.  Two modes:

* **Mock mode** (``parse_query_mock``): regex / keyword extraction — fast,
  deterministic, no API key required.  Used when ``AI_MOCK_MODE=true``.
* **Real mode** (``parse_query_real``): Claude API call that returns a
  ``ParsedQuery``.  Falls back to mock on any error.

Also provides ``sco[RESEND_KEY_REDACTED]()`` for weighted scoring of contacts against
a parsed query.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class ParsedQuery:
    """Structured representation of a natural-language contact search."""

    titles: list[str] = field(default_factory=list)
    companies: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    relationship_types: list[str] = field(default_factory=list)
    raw_query: str = ""


# ---------------------------------------------------------------------------
# Company group expansions
# ---------------------------------------------------------------------------

_COMPANY_GROUPS: dict[str, list[str]] = {
    "big tech": ["Google", "Meta", "Apple", "Amazon", "Microsoft", "Netflix"],
    "faang": ["Google", "Meta", "Apple", "Amazon", "Netflix"],
    "maang": ["Google", "Meta", "Apple", "Amazon", "Netflix"],
    "faamg": ["Google", "Meta", "Apple", "Amazon", "Microsoft"],
    "manga": ["Google", "Meta", "Apple", "Amazon", "Netflix"],
}

# Patterns that match "at <Company>" or "from <Company>"
_COMPANY_PREPOSITION_RE = re.compile(
    r"\b(?:at|from|working\s+at|who\s+work(?:s)?\s+at)\s+"
    r"([A-Z][A-Za-z0-9&.\-\s]+?)(?:\s+(?:in|who|that|and|or|,)|$)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Seniority patterns (aligned with ai_matcher.py)
# ---------------------------------------------------------------------------

_SENIORITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "c_suite",
        re.compile(
            r"\b(c[eotifsm]os?|ctos?|ceos?|cfos?|coos?|cmos?|cios?|csos?|"
            r"chiefs?|founders?|co-founders?|cofounders?|presidents?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "vp",
        re.compile(r"\b(vps?|vice\s*presidents?|svps?|evps?|avps?)\b", re.IGNORECASE),
    ),
    (
        "director",
        re.compile(r"\b(directors?)\b", re.IGNORECASE),
    ),
    (
        "manager",
        re.compile(
            r"\b(managers?|head\s+of|team\s+leads?|principals?)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "senior",
        re.compile(r"\b(senior|sr\.?|staff)\b", re.IGNORECASE),
    ),
]

# ---------------------------------------------------------------------------
# Title keywords
# ---------------------------------------------------------------------------

_TITLE_KEYWORDS: list[str] = [
    "engineer",
    "engineering",
    "software engineer",
    "product manager",
    "designer",
    "data scientist",
    "data engineer",
    "data analyst",
    "machine learning",
    "marketing",
    "sales",
    "recruiter",
    "analyst",
    "consultant",
    "researcher",
    "operations",
    "devops",
    "sre",
    "frontend",
    "backend",
    "fullstack",
    "full stack",
    "mobile",
    "ios",
    "android",
    "security",
    "infrastructure",
    "platform",
    "architect",
]

# Sort longest-first so "software engineer" matches before "engineer"
_TITLE_KEYWORDS.sort(key=len, reverse=True)

# ---------------------------------------------------------------------------
# Location keywords (covers major tech hubs)
# ---------------------------------------------------------------------------

_LOCATION_KEYWORDS: dict[str, str] = {
    # Asia
    "singapore": "Singapore",
    "hong kong": "Hong Kong",
    "tokyo": "Tokyo",
    "japan": "Japan",
    "seoul": "Seoul",
    "korea": "Korea",
    "beijing": "Beijing",
    "shanghai": "Shanghai",
    "shenzhen": "Shenzhen",
    "china": "China",
    "taipei": "Taipei",
    "taiwan": "Taiwan",
    "bangkok": "Bangkok",
    "jakarta": "Jakarta",
    "kuala lumpur": "Kuala Lumpur",
    "india": "India",
    "bangalore": "Bangalore",
    "bengaluru": "Bengaluru",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
    "hyderabad": "Hyderabad",
    # US
    "san francisco": "San Francisco",
    "sf": "San Francisco",
    "bay area": "San Francisco",
    "silicon valley": "San Francisco",
    "new york": "New York",
    "nyc": "New York",
    "seattle": "Seattle",
    "austin": "Austin",
    "boston": "Boston",
    "chicago": "Chicago",
    "los angeles": "Los Angeles",
    "la": "Los Angeles",
    "denver": "Denver",
    "portland": "Portland",
    "atlanta": "Atlanta",
    # Europe / UK
    "london": "London",
    "berlin": "Berlin",
    "amsterdam": "Amsterdam",
    "dublin": "Dublin",
    "paris": "Paris",
    "zurich": "Zurich",
    "munich": "Munich",
    "edinburgh": "Edinburgh",
    "manchester": "Manchester",
    "stockholm": "Stockholm",
    # Other
    "toronto": "Toronto",
    "vancouver": "Vancouver",
    "sydney": "Sydney",
    "melbourne": "Melbourne",
    "tel aviv": "Tel Aviv",
}

# Sort longest-first so "san francisco" matches before "sf"
_LOCATION_ENTRIES: list[tuple[str, str]] = sorted(
    _LOCATION_KEYWORDS.items(), key=lambda kv: len(kv[0]), reverse=True
)

# ---------------------------------------------------------------------------
# Relationship type mapping (natural language → enum value)
# ---------------------------------------------------------------------------

_RELATIONSHIP_MAP: dict[str, str] = {
    "former colleague": "former_colleague",
    "former coworker": "former_colleague",
    "ex-colleague": "former_colleague",
    "ex colleague": "former_colleague",
    "current colleague": "current_colleague",
    "coworker": "current_colleague",
    "colleague": "current_colleague",
    "manager": "manager",
    "my manager": "manager",
    "former manager": "manager",
    "ex-manager": "manager",
    "alumni": "alumni",
    "school": "alumni",
    "university": "alumni",
    "college": "alumni",
    "classmate": "alumni",
    "industry peer": "industry_peer",
    "peer": "industry_peer",
    "friend": "friend",
    "friends": "friend",
    "mentor": "mentor",
    "mentors": "mentor",
    "recruiter": "recruiter",
    "recruiters": "recruiter",
}

# Sort longest-first for greedy matching
_RELATIONSHIP_ENTRIES: list[tuple[str, str]] = sorted(
    _RELATIONSHIP_MAP.items(), key=lambda kv: len(kv[0]), reverse=True
)


# ---------------------------------------------------------------------------
# Private extraction helpers (keep parse_query_mock complexity manageable)
# ---------------------------------------------------------------------------


def _extract_companies(query_lower: str, original_query: str) -> tuple[list[str], str]:
    """Extract companies from the query, returning (companies, cleaned_query)."""
    companies: list[str] = []
    q_lower = query_lower

    # Expand company groups
    for group_name, group_companies in _COMPANY_GROUPS.items():
        if group_name in q_lower:
            companies.extend(group_companies)
            q_lower = q_lower.replace(group_name, " ")

    # Specific companies via preposition patterns
    for match in _COMPANY_PREPOSITION_RE.finditer(original_query):
        company = match.group(1).strip().rstrip(",")
        if company.lower() not in _COMPANY_GROUPS:
            existing_lower = {c.lower() for c in companies}
            if company.lower() not in existing_lower:
                companies.append(company)

    return companies, q_lower


def _extract_seniority(query_lower: str) -> list[str]:
    """Extract seniority levels from the query."""
    seniority: list[str] = []
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(query_lower) and level not in seniority:
            seniority.append(level)
    return seniority


def _extract_titles(query_lower: str) -> list[str]:
    """Extract title keywords from the query."""
    titles: list[str] = []
    for kw in _TITLE_KEYWORDS:
        if kw in query_lower and kw not in titles:
            titles.append(kw)
    return titles


def _extract_locations(query_lower: str) -> list[str]:
    """Extract locations from the query."""
    locations: list[str] = []
    for loc_key, loc_canonical in _LOCATION_ENTRIES:
        if loc_key in query_lower and loc_canonical not in locations:
            locations.append(loc_canonical)
    return locations


def _extract_relationship_types(query_lower: str) -> list[str]:
    """Extract relationship types from the query."""
    relationship_types: list[str] = []
    for phrase, enum_val in _RELATIONSHIP_ENTRIES:
        if phrase in query_lower and enum_val not in relationship_types:
            relationship_types.append(enum_val)
    return relationship_types


# ---------------------------------------------------------------------------
# Mock parser
# ---------------------------------------------------------------------------


def parse_query_mock(query: str) -> ParsedQuery:
    """Parse a natural-language contact search query using regex/keyword extraction.

    Returns a ``ParsedQuery`` with extracted structured filters.  If nothing
    is parseable the result has all empty lists (graceful fallback).
    """
    result = ParsedQuery(raw_query=query)
    if not query or not query.strip():
        return result

    q_lower = query.lower().strip()

    result.companies, q_lower = _extract_companies(q_lower, query)
    result.seniority = _extract_seniority(q_lower)
    result.titles = _extract_titles(q_lower)
    result.locations = _extract_locations(q_lower)
    result.relationship_types = _extract_relationship_types(q_lower)

    return result


# ---------------------------------------------------------------------------
# Contact scorer
# ---------------------------------------------------------------------------

# Seniority hierarchy for scoring (higher rank = more senior)
_SENIORITY_RANK: dict[str, int] = {
    "c_suite": 5,
    "vp": 4,
    "director": 3,
    "manager": 2,
    "senior": 1,
}


def _sco[RESEND_KEY_REDACTED](parsed: ParsedQuery, title: str | None) -> float:
    """Score a contact's title against parsed query criteria (0-100)."""
    if not title:
        return 0.0
    title_lower = title.lower()

    # Exact keyword match in title
    for kw in parsed.titles:
        if kw in title_lower:
            return 100.0

    # Seniority-level match: check if contact title matches requested seniority
    if parsed.seniority:
        for level, pattern in _SENIORITY_PATTERNS:
            if level in parsed.seniority and pattern.search(title_lower):
                # Score based on how senior the matched level is
                return 50.0 + _SENIORITY_RANK.get(level, 0) * 6.0

    # Fuzzy / synonym match: check if any query title keyword appears as a
    # substring of the contact title or vice versa
    for kw in parsed.titles:
        # Partial overlap (e.g. "engineer" in "engineering manager")
        if any(word in title_lower for word in kw.split()):
            return 70.0

    return 0.0


def _sco[RESEND_KEY_REDACTED](
    parsed: ParsedQuery, company_name: str | None, company_matched: bool
) -> float:
    """Score a contact's company against parsed query criteria (0-100)."""
    if company_matched:
        return 100.0
    if not company_name or not parsed.companies:
        return 0.0
    company_lower = company_name.lower()
    for queried in parsed.companies:
        if queried.lower() in company_lower or company_lower in queried.lower():
            return 60.0
    return 0.0


def _sco[RESEND_KEY_REDACTED](parsed: ParsedQuery, location: str | None) -> float:
    """Score a contact's location against parsed query criteria (0-100)."""
    if not location or not parsed.locations:
        return 0.0
    location_lower = location.lower()
    for queried_loc in parsed.locations:
        if queried_loc.lower() == location_lower:
            return 100.0
        # Same country heuristic: check if one contains the other
        if (
            queried_loc.lower() in location_lower
            or location_lower in queried_loc.lower()
        ):
            return 60.0
    return 0.0


def _sco[RESEND_KEY_REDACTED](parsed: ParsedQuery, relationship_type: str | None) -> float:
    """Score a contact's relationship type against parsed query criteria (0-100)."""
    if not relationship_type or not parsed.relationship_types:
        return 0.0
    if relationship_type in parsed.relationship_types:
        return 100.0
    return 0.0


def sco[RESEND_KEY_REDACTED](
    parsed: ParsedQuery,
    company_name: str | None,
    title: str | None,
    location: str | None,
    relationship_type: str | None,
    company_matched: bool,
) -> float:
    """Score a contact against a parsed query using weighted criteria.

    Weights: title 40%, company 30%, location 20%, relationship 10%.
    Only criteria that were specified in the query contribute to the score;
    weights are renormalized so they sum to 1.0.

    Returns a score from 0-100.  Contacts scoring below 20 should be
    excluded from results.
    """
    # Define base weights for each criterion
    criteria: list[tuple[float, float]] = []  # (weight, score)

    if parsed.titles or parsed.seniority:
        criteria.append((0.40, _sco[RESEND_KEY_REDACTED](parsed, title)))
    if parsed.companies:
        criteria.append((0.30, _sco[RESEND_KEY_REDACTED](parsed, company_name, company_matched)))
    if parsed.locations:
        criteria.append((0.20, _sco[RESEND_KEY_REDACTED](parsed, location)))
    if parsed.relationship_types:
        criteria.append((0.10, _sco[RESEND_KEY_REDACTED](parsed, relationship_type)))

    if not criteria:
        return 0.0

    total_weight = sum(w for w, _ in criteria)
    return sum((w / total_weight) * s for w, s in criteria)


# ---------------------------------------------------------------------------
# Real Claude API parser
# ---------------------------------------------------------------------------

_PARSE_SYSTEM_PROMPT = """\
You are a query parser for a professional contact search system.
Given a natural-language query, extract structured fields and return ONLY
valid JSON with these keys:

- titles: list of job title keywords (e.g. ["engineer", "product manager"])
- companies: list of company names. Expand shorthand:
  "big tech" -> ["Google", "Meta", "Apple", "Amazon", "Microsoft", "Netflix"]
  "faang"/"maang" -> ["Google", "Meta", "Apple", "Amazon", "Netflix"]
- seniority: list from [c_suite, vp, director, manager, senior]
- locations: list of location names (use canonical city/country names)
- relationship_types: list from [former_colleague, current_colleague, manager, \
alumni, industry_peer, friend, mentor, recruiter]

Return ONLY the JSON object. No explanation, no markdown fences."""


def parse_query_real(query: str) -> ParsedQuery:
    """Parse a query using the Claude API, falling back to mock on error."""
    try:
        import json as _json

        import anthropic

        from app.config import settings as _settings

        client = anthropic.Anthropic(api_key=_settings.ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=_settings.CLAUDE_MODEL,
            max_tokens=512,
            system=_PARSE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": query}],
        )

        text = response.content[0].text.strip()
        data = _json.loads(text)

        return ParsedQuery(
            titles=data.get("titles", []),
            companies=data.get("companies", []),
            seniority=data.get("seniority", []),
            locations=data.get("locations", []),
            relationship_types=data.get("relationship_types", []),
            raw_query=query,
        )
    except Exception:
        logger.warning("Claude parse failed for query %r, falling back to mock", query)
        return parse_query_mock(query)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def parse_query(query: str) -> ParsedQuery:
    """Parse a natural-language contact search query.

    Uses mock (regex) when ``AI_MOCK_MODE`` is true, otherwise calls the
    Claude API via ``parse_query_real``.
    """
    from app.config import settings as _settings

    if _settings.AI_MOCK_MODE:
        return parse_query_mock(query)
    return parse_query_real(query)
