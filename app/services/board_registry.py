"""Registry mapping company names to their ATS board identifiers.

Greenhouse and Lever expose free, public APIs for job listings.
This registry maps company names to their board slugs so we can
fetch openings without any auth or API keys.

Verification: run `python -m app.services.board_registry` to print all
registered companies grouped by region.
"""

from difflib import SequenceMatcher

BOARD_REGISTRY: dict[str, dict[str, str]] = {
    # --- US / Global Tech ---
    "stripe": {"greenhouse": "stripe"},
    "notion": {"lever": "notionhq"},
    "figma": {"greenhouse": "figma"},
    "airbnb": {"greenhouse": "airbnb"},
    "coinbase": {"greenhouse": "coinbase"},
    "discord": {"greenhouse": "discord"},
    "databricks": {"greenhouse": "databricks"},
    "plaid": {"greenhouse": "plaid"},
    "ramp": {"greenhouse": "ramp"},
    "brex": {"greenhouse": "brex"},
    "rippling": {"greenhouse": "rippling"},
    "scale": {"lever": "scaleai"},
    "anthropic": {"greenhouse": "anthropic"},
    "openai": {"greenhouse": "openai"},
    "spotify": {"greenhouse": "spotify"},
    "netflix": {"lever": "netflix"},
    "snap": {"greenhouse": "snapchat"},
    "doordash": {"greenhouse": "doordash"},
    "instacart": {"greenhouse": "instacart"},
    "robinhood": {"greenhouse": "robinhood"},
    "affirm": {"greenhouse": "affirm"},
    "chime": {"greenhouse": "chime"},
    "nubank": {"greenhouse": "nubank"},
    "klarna": {"greenhouse": "klarna"},
    "shopify": {"greenhouse": "shopify"},
    "twilio": {"greenhouse": "twilio"},
    "datadog": {"greenhouse": "datadog"},
    "hashicorp": {"greenhouse": "hashicorp"},
    "elastic": {"greenhouse": "elastic"},
    "cloudflare": {"greenhouse": "cloudflare"},
    # --- Singapore / Southeast Asia ---
    "grab": {"greenhouse": "grab"},
    "sea-group": {"greenhouse": "seagroup"},
    "shopee": {"greenhouse": "shopee"},
    "lazada": {"greenhouse": "lazada"},
    "gojek": {"greenhouse": "gojek"},
    "carousell": {"greenhouse": "carousell"},
    "foodpanda": {"greenhouse": "foodpanda"},
    "ninja-van": {"greenhouse": "ninjavan"},
    "patsnap": {"greenhouse": "patsnap"},
    "endowus": {"greenhouse": "endowus"},
    "syfe": {"lever": "syfe"},
    "aspire": {"greenhouse": "aspire"},
    "funding-societies": {"greenhouse": "fundingsocieties"},
    "carro": {"greenhouse": "carro"},
    # --- India ---
    "razorpay": {"greenhouse": "razorpay"},
    "zerodha": {"lever": "zerodha"},
    "cred": {"lever": "cred"},
    "meesho": {"greenhouse": "meesho"},
    "phonepe": {"greenhouse": "phonepe"},
    # --- Australia / New Zealand ---
    "canva": {"greenhouse": "canva"},
    "atlassian": {"greenhouse": "atlassian"},
    "afterpay": {"greenhouse": "afterpay"},
}

# Regional groupings for verification / display
REGIONS: dict[str, list[str]] = {
    "US / Global": [
        "stripe",
        "notion",
        "figma",
        "airbnb",
        "coinbase",
        "discord",
        "databricks",
        "plaid",
        "ramp",
        "brex",
        "rippling",
        "scale",
        "anthropic",
        "openai",
        "spotify",
        "netflix",
        "snap",
        "doordash",
        "instacart",
        "robinhood",
        "affirm",
        "chime",
        "nubank",
        "klarna",
        "shopify",
        "twilio",
        "datadog",
        "hashicorp",
        "elastic",
        "cloudflare",
    ],
    "Singapore / SEA": [
        "grab",
        "sea-group",
        "shopee",
        "lazada",
        "gojek",
        "carousell",
        "foodpanda",
        "ninja-van",
        "patsnap",
        "endowus",
        "syfe",
        "aspire",
        "funding-societies",
        "carro",
    ],
    "India": ["razorpay", "zerodha", "cred", "meesho", "phonepe"],
    "Australia / NZ": ["canva", "atlassian", "afterpay"],
}


# Reverse lookup: company_key → region name
_KEY_TO_REGION: dict[str, str] = {}
for _region, _keys in REGIONS.items():
    for _key in _keys:
        _KEY_TO_REGION[_key] = _region

# Location keywords → region names (for user target_locations matching)
_LOCATION_TO_REGIONS: dict[str, list[str]] = {
    "singapore": ["Singapore / SEA"],
    "sea": ["Singapore / SEA"],
    "southeast asia": ["Singapore / SEA"],
    "malaysia": ["Singapore / SEA"],
    "indonesia": ["Singapore / SEA"],
    "vietnam": ["Singapore / SEA"],
    "thailand": ["Singapore / SEA"],
    "philippines": ["Singapore / SEA"],
    "india": ["India"],
    "mumbai": ["India"],
    "bangalore": ["India"],
    "delhi": ["India"],
    "australia": ["Australia / NZ"],
    "new zealand": ["Australia / NZ"],
    "sydney": ["Australia / NZ"],
    "melbourne": ["Australia / NZ"],
    "us": ["US / Global"],
    "united states": ["US / Global"],
    "san francisco": ["US / Global"],
    "new york": ["US / Global"],
    "remote": ["US / Global", "Singapore / SEA", "India", "Australia / NZ"],
}


def get_display_name(company_key: str) -> str:
    """Return a human-readable display name for a board registry key.

    Uses the key directly with title-casing as fallback for unknown keys.
    """
    return company_key.replace("-", " ").title()


def get_region(company_key: str) -> str | None:
    """Return the region name for a company key, or None if unknown."""
    return _KEY_TO_REGION.get(company_key)


def companies_for_locations(target_locations: list[str] | None) -> list[str]:
    """Return board registry keys relevant to the user's target locations.

    If no locations specified or none match, returns all companies.
    Prioritizes matched-region companies first, then appends the rest.
    """
    if not target_locations:
        return list(BOARD_REGISTRY.keys())

    matched_regions: set[str] = set()
    for loc in target_locations:
        loc_lower = loc.strip().lower()
        for keyword, regions in _LOCATION_TO_REGIONS.items():
            if keyword in loc_lower or loc_lower in keyword:
                matched_regions.update(regions)

    if not matched_regions:
        return list(BOARD_REGISTRY.keys())

    # Prioritized list: matched regions first, then others
    prioritized: list[str] = []
    rest: list[str] = []
    for key in BOARD_REGISTRY:
        region = _KEY_TO_REGION.get(key)
        if region in matched_regions:
            prioritized.append(key)
        else:
            rest.append(key)

    return prioritized + rest


def lookup_boards(company_name: str) -> dict[str, str] | None:
    """Look up board identifiers for a company name (case-insensitive, fuzzy).

    Returns the board dict if found, or None if no match above threshold.
    """
    key = company_name.strip().lower()

    # Exact match
    if key in BOARD_REGISTRY:
        return BOARD_REGISTRY[key]

    # Fuzzy match — require >= 0.8 similarity
    best_match: str | None = None
    best_score = 0.0
    for registry_key in BOARD_REGISTRY:
        score = SequenceMatcher(None, key, registry_key).ratio()
        if score > best_score:
            best_score = score
            best_match = registry_key

    if best_match is not None and best_score >= 0.8:
        return BOARD_REGISTRY[best_match]

    return None


def register_board(company_name: str, source: str, board_id: str) -> None:
    """Register a new board mapping at runtime."""
    key = company_name.strip().lower()
    if key not in BOARD_REGISTRY:
        BOARD_REGISTRY[key] = {}
    BOARD_REGISTRY[key][source] = board_id


if __name__ == "__main__":
    print(f"Board Registry — {len(BOARD_REGISTRY)} companies\n")
    for region, companies in REGIONS.items():
        print(f"  {region} ({len(companies)}):")
        for name in companies:
            entry = BOARD_REGISTRY.get(name, {})
            sources = ", ".join(f"{k}={v}" for k, v in entry.items())
            status = sources if sources else "MISSING"
            print(f"    {name:25s} {status}")
        print()
