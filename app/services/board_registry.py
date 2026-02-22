"""Registry mapping company names to their ATS board identifiers.

Greenhouse and Lever expose free, public APIs for job listings.
This registry maps company names to their board slugs so we can
fetch openings without any auth or API keys.

Verification: run `python -m app.services.board_registry` to print all
registered companies grouped by region.
"""

import asyncio
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
    "gitlab": {"greenhouse": "gitlab"},
    "vercel": {"greenhouse": "vercel"},
    "linear": {"ashby": "linear"},
    "deel": {"ashby": "deel"},
    "remote-com": {"greenhouse": "remotecom"},
    # --- Top Startups (SF Bay Area) ---
    "render": {"ashby": "render"},
    "harmonic": {"greenhouse": "harmonic"},
    "ambience-healthcare": {"ashby": "ambiencehealthcare"},
    "vanta": {"ashby": "vanta"},
    "harvey": {"ashby": "harvey"},
    "clickhouse": {"greenhouse": "clickhouse"},
    "applied-intuition": {"greenhouse": "appliedintuition"},
    "glean": {"greenhouse": "gleanwork"},
    "semgrep": {"ashby": "semgrep"},
    "hightouch": {"greenhouse": "hightouch"},
    "persona": {"ashby": "persona"},
    # --- Top Startups (New York) ---
    "rilla": {"ashby": "rilla"},
    "adaptive-security": {"ashby": "adaptivesecurity"},
    "traba": {"ashby": "traba"},
    "tennr": {"ashby": "tennr"},
    "kalshi": {"greenhouse": "kalshi"},
    "stainless": {"ashby": "stainlessapi"},
    "grafana": {"greenhouse": "grafanalabs"},
    # --- Singapore / Southeast Asia ---
    "google": {"career_page": "https://www.google.com/about/careers/applications/"},
    "meta": {"career_page": "https://www.metacareers.com/jobs/"},
    "grab": {"career_page": "https://grab.careers/jobs/"},
    "sea-group": {"career_page": "https://career.sea.com/"},
    "shopee": {"career_page": "https://careers.shopee.sg/"},
    "lazada": {"career_page": "https://www.lazada.com/en/careers/"},
    "gojek": {"career_page": "https://www.gojek.io/careers"},
    "carousell": {"career_page": "https://careers.carousell.com/"},
    "foodpanda": {"career_page": "https://careers.foodpanda.com/"},
    "ninja-van": {"lever": "ninjavan"},
    "patsnap": {"lever": "patsnap"},
    "endowus": {"career_page": "https://endowus.com/careers"},
    "syfe": {"career_page": "https://www.syfe.com/careers"},
    "aspire": {"greenhouse": "aspireio"},
    "funding-societies": {"career_page": "https://fundingsocieties.com/career"},
    "carro": {"career_page": "https://careers.carro.sg/jobs/Careers"},
    "bytedance": {"career_page": "https://jobs.bytedance.com/en/"},
    "tiktok": {"career_page": "https://careers.tiktok.com/"},
    "wise": {"career_page": "https://www.wise.jobs/"},
    "revolut": {"career_page": "https://www.revolut.com/careers/"},
    "propertyguru": {"greenhouse": "propertyguru"},
    "circles-life": {"career_page": "https://www.circles.life/sg/careers/"},
    "traveloka": {"career_page": "https://www.traveloka.com/en-sg/careers"},
    "goto": {"career_page": "https://www.gotocompany.com/careers"},
    "binance": {"career_page": "https://www.binance.com/en/careers"},
    "crypto-com": {"lever": "crypto"},
    "govtech": {"career_page": "https://www.tech.gov.sg/careers/"},
    "shopback": {"career_page": "https://careers.shopback.com/"},
    "dbs": {"career_page": "https://www.dbs.com/careers/"},
    "ocbc": {"career_page": "https://www.ocbc.com/group/careers"},
    "uob": {"career_page": "https://www.uobgroup.com/careers/"},
    "standard-chartered": {"career_page": "https://www.sc.com/en/careers/"},
    "nium": {"lever": "nium"},
    "monks-hill": {"career_page": "https://www.monkshill.com/careers"},
    # --- Singapore MNCs (ST Best Employers 2025) ---
    "amazon": {"career_page": "https://www.amazon.jobs/en/"},
    "apple": {"career_page": "https://jobs.apple.com/en-sg/search"},
    "salesforce": {"career_page": "https://careers.salesforce.com/en/jobs/"},
    "oracle": {"career_page": "https://careers.oracle.com/"},
    "ibm": {"career_page": "https://www.ibm.com/careers/"},
    "intel": {"career_page": "https://jobs.intel.com/"},
    "hp": {"career_page": "https://jobs.hp.com/"},
    "qualcomm": {"career_page": "https://careers.qualcomm.com/"},
    "sap": {"career_page": "https://jobs.sap.com/"},
    "autodesk": {"career_page": "https://www.autodesk.com/careers/"},
    "mastercard": {"career_page": "https://careers.mastercard.com/"},
    "boeing": {"career_page": "https://jobs.boeing.com/"},
    "rolls-royce": {"career_page": "https://careers.rolls-royce.com/"},
    "siemens": {"career_page": "https://jobs.siemens.com/"},
    "siemens-energy": {"career_page": "https://jobs.siemens-energy.com/"},
    "siemens-digital-industries": {
        "career_page": "https://www.sw.siemens.com/en-US/careers/"
    },
    "hexagon": {"lever": "hexagonusfederal"},
    "schneider-electric": {"career_page": "https://www.se.com/ww/en/about-us/careers/"},
    "cognizant": {"career_page": "https://careers.cognizant.com/"},
    "micron": {"career_page": "https://careers.micron.com/"},
    "sony": {"career_page": "https://www.sony.com/en/careers/"},
    "goldman-sachs": {"career_page": "https://www.goldmansachs.com/careers/"},
    "jpmorgan": {"career_page": "https://careers.jpmorgan.com/"},
    "hsbc": {"career_page": "https://www.hsbc.com/careers/"},
    "citibank": {"career_page": "https://jobs.citi.com/"},
    "deutsche-bank": {"career_page": "https://careers.db.com/"},
    "bank-of-america": {"career_page": "https://campus.bankofamerica.com/careers/"},
    "singtel": {"career_page": "https://www.singtel.com/about-us/careers"},
    "st-engineering": {"career_page": "https://www.stengg.com/careers/"},
    "temasek": {"career_page": "https://www.temasek.com.sg/en/careers"},
    "gic": {"greenhouse": "gic"},
    "capitaland": {"career_page": "https://www.capitaland.com/en/careers.html"},
    "keppel": {"career_page": "https://www.keppel.com/careers"},
    "singapore-airlines": {
        "career_page": "https://www.singaporeair.com/en_UK/sg/careers/"
    },
    # --- India ---
    "razorpay": {"greenhouse": "razorpay"},
    "zerodha": {"lever": "zerodha"},
    "cred": {"lever": "cred"},
    "meesho": {"greenhouse": "meesho"},
    "phonepe": {"greenhouse": "phonepe"},
    "flipkart": {"career_page": "https://www.flipkartcareers.com/"},
    "swiggy": {"career_page": "https://careers.swiggy.com/"},
    # --- Australia / New Zealand ---
    "canva": {"greenhouse": "canva"},
    "atlassian": {"greenhouse": "atlassian"},
    "afterpay": {"greenhouse": "afterpay"},
    "xero": {"greenhouse": "xero"},
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
        "meta",
        "amazon",
        "apple",
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
        "gitlab",
        "vercel",
        "linear",
        "deel",
        "remote-com",
        "salesforce",
        "oracle",
        "ibm",
        "intel",
        "hp",
        "qualcomm",
        "sap",
        "autodesk",
        "mastercard",
        "boeing",
        "rolls-royce",
        "siemens",
        "siemens-energy",
        "siemens-digital-industries",
        "hexagon",
        "schneider-electric",
        "cognizant",
        "micron",
        "sony",
        "goldman-sachs",
        "jpmorgan",
        "hsbc",
        "citibank",
        "deutsche-bank",
        "bank-of-america",
        "render",
        "harmonic",
        "ambience-healthcare",
        "vanta",
        "harvey",
        "clickhouse",
        "applied-intuition",
        "glean",
        "semgrep",
        "hightouch",
        "persona",
        "rilla",
        "adaptive-security",
        "traba",
        "tennr",
        "kalshi",
        "stainless",
        "grafana",
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
        "bytedance",
        "tiktok",
        "wise",
        "revolut",
        "propertyguru",
        "circles-life",
        "traveloka",
        "goto",
        "binance",
        "crypto-com",
        "govtech",
        "dbs",
        "ocbc",
        "uob",
        "standard-chartered",
        "shopback",
        "nium",
        "monks-hill",
        "singtel",
        "st-engineering",
        "temasek",
        "gic",
        "capitaland",
        "keppel",
        "singapore-airlines",
    ],
    "India": [
        "razorpay",
        "zerodha",
        "cred",
        "meesho",
        "phonepe",
        "flipkart",
        "swiggy",
    ],
    "Australia / NZ": ["canva", "atlassian", "afterpay", "xero"],
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
    "sea-group": "https://career.sea.com/",
    "shopee": "https://careers.shopee.sg/",
    "gojek": "https://www.gojek.io/careers",
    "carousell": "https://careers.carousell.com/",
    "ninja-van": "https://www.ninjavan.co/en-sg/careers",
    "canva": "https://www.canva.com/careers/",
    "atlassian": "https://www.atlassian.com/company/careers",
    "razorpay": "https://razorpay.com/jobs/",
    "phonepe": "https://www.phonepe.com/careers/",
    "bytedance": "https://jobs.bytedance.com/en/",
    "tiktok": "https://careers.tiktok.com/",
    "wise": "https://www.wise.jobs/",
    "revolut": "https://www.revolut.com/careers/",
    "propertyguru": "https://careers.propertyguru.com/",
    "circles-life": "https://www.circles.life/sg/careers/",
    "traveloka": "https://www.traveloka.com/en-sg/careers",
    "goto": "https://www.gotocompany.com/careers",
    "binance": "https://www.binance.com/en/careers",
    "crypto-com": "https://crypto.com/careers",
    "govtech": "https://www.tech.gov.sg/careers/",
    "dbs": "https://www.dbs.com/careers/",
    "ocbc": "https://www.ocbc.com/group/careers",
    "uob": "https://www.uobgroup.com/careers/",
    "standard-chartered": "https://www.sc.com/en/careers/",
    "shopback": "https://careers.shopback.com/",
    "nium": "https://www.nium.com/careers",
    "flipkart": "https://www.flipkartcareers.com/",
    "swiggy": "https://careers.swiggy.com/",
    "xero": "https://www.xero.com/careers/",
    "meta": "https://www.metacareers.com/",
    "gitlab": "https://about.gitlab.com/jobs/",
    "vercel": "https://vercel.com/careers",
    "linear": "https://linear.app/careers",
    "deel": "https://www.deel.com/careers",
    "remote-com": "https://remote.com/careers",
    # MNCs with SG presence (ST Best Employers 2025)
    "amazon": "https://www.amazon.jobs/en/",
    "apple": "https://jobs.apple.com/en-sg/search",
    "salesforce": "https://careers.salesforce.com/en/jobs/",
    "oracle": "https://careers.oracle.com/",
    "ibm": "https://www.ibm.com/careers/",
    "intel": "https://jobs.intel.com/",
    "hp": "https://jobs.hp.com/",
    "qualcomm": "https://careers.qualcomm.com/",
    "sap": "https://jobs.sap.com/",
    "autodesk": "https://www.autodesk.com/careers/",
    "mastercard": "https://careers.mastercard.com/",
    "boeing": "https://jobs.boeing.com/",
    "rolls-royce": "https://careers.rolls-royce.com/",
    "siemens": "https://jobs.siemens.com/",
    "schneider-electric": "https://www.se.com/ww/en/about-us/careers/",
    "cognizant": "https://careers.cognizant.com/",
    "micron": "https://careers.micron.com/",
    "sony": "https://www.sony.com/en/careers/",
    "goldman-sachs": "https://www.goldmansachs.com/careers/",
    "jpmorgan": "https://careers.jpmorgan.com/",
    "hsbc": "https://www.hsbc.com/careers/",
    "citibank": "https://jobs.citi.com/",
    "deutsche-bank": "https://careers.db.com/",
    "bank-of-america": "https://campus.bankofamerica.com/careers/",
    "singtel": "https://www.singtel.com/about-us/careers",
    "st-engineering": "https://www.stengg.com/careers/",
    "temasek": "https://www.temasek.com.sg/en/careers",
    "gic": "https://www.gic.com.sg/careers/",
    "capitaland": "https://www.capitaland.com/en/careers.html",
    "keppel": "https://www.keppel.com/careers",
    "singapore-airlines": "https://www.singaporeair.com/en_UK/sg/careers/",
    # Top Startups (SF Bay Area + New York)
    "render": "https://render.com/careers",
    "harmonic": "https://www.harmonic.ai/careers",
    "ambience-healthcare": "https://www.ambiencehealthcare.com/careers",
    "vanta": "https://www.vanta.com/careers",
    "harvey": "https://www.harvey.ai/careers",
    "clickhouse": "https://clickhouse.com/careers",
    "applied-intuition": "https://www.appliedintuition.com/careers",
    "glean": "https://www.glean.com/careers",
    "semgrep": "https://semgrep.dev/careers",
    "hightouch": "https://hightouch.com/careers",
    "persona": "https://withpersona.com/careers",
    "rilla": "https://www.rilla.com/careers",
    "adaptive-security": "https://www.adaptive.security/careers",
    "traba": "https://www.traba.work/careers",
    "tennr": "https://www.tennr.com/careers",
    "kalshi": "https://kalshi.com/careers",
    "stainless": "https://www.stainlessapi.com/careers",
    "grafana": "https://grafana.com/about/careers/",
}


def lookup_careers_url(company_name: str) -> str | None:
    """Return the careers page URL for a company, if known.

    Strips common domain suffixes (.ai, .io, etc.) so 'cantina.ai' finds 'cantina'.
    """
    import re

    key = company_name.strip().lower()
    url = CAREERS_URLS.get(key)
    if url:
        return url
    # Strip domain suffix and retry
    stripped = re.sub(r"\.(ai|io|com|co|dev|app|tech|xyz|org|net)$", "", key)
    if stripped != key:
        return CAREERS_URLS.get(stripped)
    return None


def is_known_tech_company(company_key: str) -> bool:
    """Return True if the company is in the board registry (all tech/SaaS)."""
    return company_key.strip().lower() in BOARD_REGISTRY


def get_display_name(company_key: str) -> str:
    """Return a human-readable display name for a board registry key.

    Uses the key directly with title-casing as fallback for unknown keys.
    """
    return company_key.replace("-", " ").title()


def get_region(company_key: str) -> str | None:
    """Return the region name for a company key, or None if unknown."""
    return _KEY_TO_REGION.get(company_key)


def companies_for_locations(target_locations: list[str] | None) -> list[str]:
    """Return all board registry keys.

    Companies are not filtered or prioritised by region because MNCs
    (Google, Amazon, Goldman Sachs, etc.) have roles in many regions.
    Location-based filtering happens downstream at the individual-job
    level during role matching.
    """
    return list(BOARD_REGISTRY.keys())


def lookup_boards(company_name: str) -> dict[str, str] | None:
    """Look up board identifiers for a company name (case-insensitive, fuzzy).

    Strips common domain suffixes (.ai, .io, etc.) before matching.
    Returns the board dict if found, or None if no match above threshold.
    """
    import re

    key = company_name.strip().lower()

    # Exact match
    if key in BOARD_REGISTRY:
        return BOARD_REGISTRY[key]

    # Strip domain suffix and retry exact match
    stripped = re.sub(r"\.(ai|io|com|co|dev|app|tech|xyz|org|net)$", "", key)
    if stripped != key and stripped in BOARD_REGISTRY:
        return BOARD_REGISTRY[stripped]

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
_NON_ALNUM = re.compile(
    r"[^a-z0-9\s-]+"
)  # Replace (not remove) to preserve word boundaries
_MULTI_DASH = re.compile(r"-{2,}")

_PROBE_TIMEOUT = 5.0


def _slug_candidates(company_name: str) -> list[str]:
    """Generate plausible ATS slugs from a company name.

    Examples:
        "Ninja Van" → ["ninja-van", "ninjavan"]
        "ByteDance, Inc." → ["bytedance"]
        "Sea Group" → ["sea-group", "seagroup", "sea"]
        "Cantina.ai" → ["cantina"]
    """
    name = company_name.strip().lower()
    # Replace non-alnum with space (not empty) to preserve word boundaries
    # so "cantina.ai" → "cantina ai" (not "cantinai")
    name = _NON_ALNUM.sub(" ", name)
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
        except (httpx.HTTPError, ImportError):
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
            logger.info(
                "Discovered ATS for '%s' via slug '%s': %s", company_name, slug, result
            )
            return result

    logger.info("No ATS discovered for '%s' (tried %s)", company_name, candidates)
    return None


async def lookup_or_discover_boards(
    company_name: str, db: AsyncSession
) -> tuple[dict[str, str] | None, bool]:
    """Look up boards from DB, static registry, cache, or live discovery.

    Returns (boards_dict, was_discovered) where was_discovered is True
    when the board was found via auto-discovery (not static registry/DB).
    """
    # 0. Check DB-backed registry first
    from app.services.registry_service import lookup_boards_db

    db_boards = await lookup_boards_db(db, company_name)
    if db_boards is not None:
        return db_boards, False

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

    if cached is not None and cached.expires_at > datetime.now(timezone.utc):
        data = cached.data
        if data.get("boards"):
            return data["boards"], True
        return None, False
    # Expired — will re-probe below

    # 3. Live probe
    discovered = await discover_boards(company_name)

    # 4. Cache the result (even None to avoid repeated probes)
    #    Use a savepoint so a concurrent-insert race doesn't poison the
    #    outer transaction (two requests can discover the same company
    #    simultaneously; the second INSERT hits the unique constraint).
    cache_data = {"boards": discovered}
    expires = datetime.now(timezone.utc) + timedelta(days=7)

    if cached is not None:
        cached.data = cache_data
        cached.expires_at = expires
        await db.flush()
    else:
        from sqlalchemy.exc import IntegrityError

        try:
            async with db.begin_nested():
                cached = EnrichmentCache(
                    cache_key=cache_key,
                    source="board_discovery",
                    data=cache_data,
                    expires_at=expires,
                )
                db.add(cached)
                await db.flush()
        except IntegrityError:
            # Concurrent request already inserted — update it instead
            result = await db.execute(
                select(EnrichmentCache).where(EnrichmentCache.cache_key == cache_key)
            )
            cached = result.scalar_one()
            cached.data = cache_data
            cached.expires_at = expires
            await db.flush()

    # 5. If found, register in-memory and persist to DB
    if discovered:
        for source, slug in discovered.items():
            register_board(company_name, source, slug)

        # Persist to company_boards table for future lookups
        from app.services.registry_service import get_board_by_key

        key = company_name.strip().lower()
        existing_db = await get_board_by_key(db, key)
        if existing_db is None:
            from app.models.registry import CompanyBoard

            source = list(discovered.keys())[0]
            slug = discovered[source]
            new_board = CompanyBoard(
                company_key=key,
                display_name=key.replace("-", " ").title(),
                board_source=source,
                board_slug=slug,
                is_active=True,
                verified_at=datetime.now(timezone.utc),
            )
            db.add(new_board)
            await db.flush()

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
