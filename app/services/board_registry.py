"""Registry mapping company names to their ATS board identifiers.

Greenhouse and Lever expose free, public APIs for job listings.
This registry maps company names to their board slugs so we can
fetch openings without any auth or API keys.

Verification: run `python -m app.services.board_registry` to print all
registered companies grouped by region.
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BOARD_REGISTRY: dict[str, dict[str, str]] = {
    # --- US / Global Tech ---
    "stripe": {"greenhouse": "stripe"},
    "notion": {"ashby": "notion"},
    "figma": {"greenhouse": "figma"},
    "airbnb": {"greenhouse": "airbnb"},
    "coinbase": {"greenhouse": "coinbase"},
    "discord": {"greenhouse": "discord"},
    "databricks": {"greenhouse": "databricks"},
    "plaid": {"ashby": "plaid-inc"},
    "ramp": {"ashby": "ramp"},
    "brex": {"greenhouse": "brex"},
    "rippling": {"greenhouse": "rippling"},
    "scale": {"lever": "scaleai"},
    "anthropic": {"greenhouse": "anthropic"},
    "openai": {"ashby": "openai"},
    "spotify": {"lever": "spotify"},
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
    "google": {"career_page": "https://www.google.com/about/careers/applications/jobs/results"},
    "grab": {"career_page": "https://grab.careers/jobs/"},
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
        "google",
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


# Fallback career page URLs — shown to users when no ATS jobs are found.
# Keys are normalised company names; values are the best public careers URL.
CAREERS_URLS: dict[str, str] = {
    "stripe": "https://stripe.com/jobs",
    "notion": "https://www.notion.so/careers",
    "figma": "https://www.figma.com/careers/",
    "airbnb": "https://careers.airbnb.com/",
    "coinbase": "https://www.coinbase.com/careers",
    "discord": "https://discord.com/careers",
    "databricks": "https://www.databricks.com/company/careers",
    "plaid": "https://plaid.com/careers/",
    "ramp": "https://ramp.com/careers",
    "brex": "https://www.brex.com/careers",
    "rippling": "https://www.rippling.com/careers",
    "scale": "https://scale.com/careers",
    "anthropic": "https://www.anthropic.com/careers",
    "openai": "https://openai.com/careers/",
    "google": "https://www.google.com/about/careers/applications/",
    "spotify": "https://www.lifeatspotify.com/jobs",
    "netflix": "https://jobs.netflix.com/",
    "snap": "https://careers.snap.com/",
    "doordash": "https://careers.doordash.com/",
    "instacart": "https://instacart.careers/",
    "robinhood": "https://careers.robinhood.com/",
    "shopify": "https://www.shopify.com/careers",
    "grab": "https://grab.careers/",
    "sea-group": "https://careers.sea.com/",
    "shopee": "https://careers.shopee.sg/",
    "gojek": "https://www.gojek.com/en-id/careers/",
    "carousell": "https://careers.carousell.com/",
    "ninja-van": "https://www.ninjavan.co/en-sg/careers",
    "canva": "https://www.canva.com/careers/",
    "atlassian": "https://www.atlassian.com/company/careers",
    "razorpay": "https://razorpay.com/jobs/",
    "phonepe": "https://www.phonepe.com/careers/",
}


def lookup_careers_url(company_name: str) -> str | None:
    """Return the careers page URL for a company, if known."""
    key = company_name.strip().lower()
    return CAREERS_URLS.get(key)


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


# ---------------------------------------------------------------------------
# Auto-discovery: probe Greenhouse / Lever / Ashby for unknown companies
# ---------------------------------------------------------------------------

_COMMON_SUFFIXES = re.compile(
    r"\b(inc|ltd|pte|co|corp|group|hq|limited|llc|technologies|tech|labs|ai)\b",
    re.IGNORECASE,
)
_NON_ALNUM = re.compile(r"[^a-z0-9\s-]")
_MULTI_DASH = re.compile(r"-{2,}")

_PROBE_TIMEOUT = 5.0


def _slug_candidates(company_name: str) -> list[str]:
    """Generate plausible ATS slugs from a company name.

    Examples:
        "Ninja Van" → ["ninja-van", "ninjavan"]
        "ByteDance, Inc." → ["bytedance"]
        "Sea Group" → ["sea-group", "seagroup", "sea"]
    """
    name = company_name.strip().lower()
    name = _NON_ALNUM.sub("", name)
    name = _COMMON_SUFFIXES.sub("", name).strip()
    name = _MULTI_DASH.sub("-", name).strip("-")

    if not name:
        return []

    candidates: list[str] = []

    # Dashed form: "ninja van" → "ninja-van"
    dashed = re.sub(r"\s+", "-", name).strip("-")
    if dashed:
        candidates.append(dashed)

    # Joined form: "ninja van" → "ninjavan"
    joined = re.sub(r"[\s-]+", "", name)
    if joined and joined != dashed:
        candidates.append(joined)

    # First-word-only form: "sea group" → "sea" (only if multi-word)
    words = name.split()
    if len(words) > 1 and words[0] not in candidates:
        candidates.append(words[0])

    return candidates


async def _probe_ats(slug: str) -> dict[str, str] | None:
    """Probe Greenhouse, Lever, and Ashby HEAD endpoints for a slug.

    Returns the first match as {"greenhouse": slug} etc., or None.
    """
    urls = [
        ("greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"),
        ("lever", f"https://api.lever.co/v0/postings/{slug}"),
        ("ashby", f"https://api.ashbyhq.com/posting-api/job-board/{slug}"),
    ]

    async def _check(source: str, url: str) -> tuple[str, bool]:
        try:
            async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT) as client:
                resp = await client.head(url)
                return (source, resp.status_code == 200)
        except httpx.HTTPError:
            return (source, False)

    results = await asyncio.gather(*[_check(src, url) for src, url in urls])
    for source, found in results:
        if found:
            return {source: slug}
    return None


async def discover_boards(company_name: str) -> dict[str, str] | None:
    """Probe ATS platforms for a company using slug candidates.

    Returns the first match (e.g. {"greenhouse": "bytedance"}) or None.
    """
    candidates = _slug_candidates(company_name)
    if not candidates:
        return None

    for slug in candidates:
        result = await _probe_ats(slug)
        if result is not None:
            logger.info("Discovered ATS for '%s' via slug '%s': %s", company_name, slug, result)
            return result

    logger.info("No ATS discovered for '%s' (tried %s)", company_name, candidates)
    return None


async def lookup_or_discover_boards(
    company_name: str, db: AsyncSession
) -> tuple[dict[str, str] | None, bool]:
    """Look up boards from registry, cache, or live discovery.

    Returns (boards_dict, was_discovered) where was_discovered is True
    when the board was found via auto-discovery (not static registry).
    """
    # 1. Check static registry (includes fuzzy match)
    boards = lookup_boards(company_name)
    if boards is not None:
        return boards, False

    # 2. Check EnrichmentCache
    from app.models.enrichment import EnrichmentCache

    cache_key = f"board_discovery:{company_name.strip().lower()}"
    result = await db.execute(
        select(EnrichmentCache).where(EnrichmentCache.cache_key == cache_key)
    )
    cached = result.scalar_one_or_none()

    if cached is not None:
        if cached.expires_at > datetime.now(timezone.utc):
            data = cached.data
            if data.get("boards"):
                return data["boards"], True
            return None, False
        # Expired — will re-probe below

    # 3. Live probe
    discovered = await discover_boards(company_name)

    # 4. Cache the result (even None to avoid repeated probes)
    cache_data = {"boards": discovered}
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    if cached is not None:
        cached.data = cache_data
        cached.expires_at = expires
    else:
        cached = EnrichmentCache(
            cache_key=cache_key,
            source="board_discovery",
            data=cache_data,
            expires_at=expires,
        )
        db.add(cached)

    await db.flush()

    # 5. If found, register in-memory for this process
    if discovered:
        for source, slug in discovered.items():
            register_board(company_name, source, slug)
        return discovered, True

    return None, False


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
