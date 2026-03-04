"""Network-driven recommendation service.

Finds companies where a user has the strongest referral network by merging
two data sources:
  1. User's own contacts (private vault)
  2. Marketplace listings from opted-in network holders (anonymised index)

Returns a ranked list of companies sorted by network_density (own + extended).
"""

import logging
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.contact import Contact
from app.models.marketplace import MarketplaceListing, NetworkSharingPreferences
from app.services.board_registry import is_known_tech_company, lookup_careers_url
from app.services.company_normalizer import normalize_company_name

logger = logging.getLogger(__name__)

# Companies that are not real employers — exclude from recommendations
_EXCLUDED_COMPANIES = {
    "freelance",
    "self-employed",
    "self employed",
    "independent",
    "independent consultant",
    "freelancer",
    "consultant",
    "unemployed",
    "retired",
    "student",
    "n/a",
    "none",
    "-",
}


_TECH_INDUSTRY_KEYWORDS = {
    "tech",
    "technology",
    "saas",
    "software",
    "fintech",
    "ai",
    "cloud",
    "internet",
    "platform",
    "digital",
}


def _wants_tech(target_industries: list[str] | None) -> bool:
    """Return True if the user's target industries indicate tech/SaaS preference."""
    if not target_industries:
        return False
    return any(
        kw in ind.lower() for ind in target_industries for kw in _TECH_INDUSTRY_KEYWORDS
    )


async def get_network_recommendations(
    user_id: uuid.UUID,
    target_locations: list[str] | None,
    exclude_companies: list[str] | None,
    target_industries: list[str] | None,
    limit: int,
    db: AsyncSession,
) -> list[dict]:
    """Return companies ranked by the user's combined network density.

    Merges the user's own contacts with marketplace listings from opted-in,
    non-paused network holders. Each company entry includes own_contacts count,
    marketplace_listings count, total network_density, a human-readable label,
    and an optional careers URL from the board registry.
    """
    # Normalise exclusions for case-insensitive comparison
    excluded = {c.strip().lower() for c in (exclude_companies or [])}

    # ------------------------------------------------------------------
    # Source 1: User's own contacts grouped by company
    # ------------------------------------------------------------------
    own_query = (
        select(
            func.lower(Company.name).label("company_key"),
            Company.name.label("display_name"),
            func.count(Contact.id).label("contact_count"),
        )
        .join(Company, Contact.company_id == Company.id)
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.company_id.isnot(None),
        )
        .group_by(func.lower(Company.name), Company.name)
    )

    own_result = await db.execute(own_query)
    own_rows = own_result.all()

    # ------------------------------------------------------------------
    # Source 2: Marketplace listings from opted-in, non-paused holders
    # ------------------------------------------------------------------
    opted_in_subq = (
        select(NetworkSharingPreferences.user_id)
        .where(
            NetworkSharingPreferences.opt_in_marketplace.is_(True),
            NetworkSharingPreferences.is_paused.is_(False),
        )
        .subquery()
    )

    market_query = (
        select(
            func.lower(Company.name).label("company_key"),
            Company.name.label("display_name"),
            func.count(MarketplaceListing.id).label("listing_count"),
        )
        .join(Company, MarketplaceListing.company_id == Company.id)
        .where(
            MarketplaceListing.is_available.is_(True),
            MarketplaceListing.deleted_at.is_(None),
            MarketplaceListing.network_holder_id.in_(select(opted_in_subq)),
            MarketplaceListing.network_holder_id != user_id,
        )
        .group_by(func.lower(Company.name), Company.name)
    )

    market_result = await db.execute(market_query)
    market_rows = market_result.all()

    # ------------------------------------------------------------------
    # Merge both sources by normalised company name
    # ------------------------------------------------------------------
    merged: dict[str, dict] = defaultdict(
        lambda: {"display_name": "", "own": 0, "market": 0}
    )

    # Helper: normalize a lowercased company key to merge variants like
    # "singapore economic development board" and
    # "singapore economic development board (edb)".
    _norm_cache: dict[str, str] = {}

    def _norm_key(raw_key: str) -> str:
        if raw_key in _norm_cache:
            return _norm_cache[raw_key]
        normed = normalize_company_name(raw_key)
        canonical = normed.lower() if normed else raw_key
        _norm_cache[raw_key] = canonical
        return canonical

    for row in own_rows:
        key = _norm_key(row.company_key)
        # Keep the longest display_name variant (more descriptive)
        if len(row.display_name) > len(merged[key]["display_name"]):
            merged[key]["display_name"] = row.display_name
        merged[key]["own"] += row.contact_count

    for row in market_rows:
        key = _norm_key(row.company_key)
        if len(row.display_name) > len(merged[key]["display_name"]):
            merged[key]["display_name"] = row.display_name
        merged[key]["market"] += row.listing_count

    # ------------------------------------------------------------------
    # Build result list
    # ------------------------------------------------------------------
    tech_filter = _wants_tech(target_industries)

    results: list[dict] = []
    for key, data in merged.items():
        if key in excluded or key in _EXCLUDED_COMPANIES or len(key) < 2:
            continue
        # When user targets tech/SaaS, skip companies not in the board registry
        if tech_filter and not is_known_tech_company(key):
            continue

        own = data["own"]
        market = data["market"]
        density = own + market

        label = _build_network_label(own, market)

        results.append(
            {
                "company_name": key,
                "display_name": data["display_name"],
                "source": "network_signal",
                "network_density": density,
                "network_label": label,
                "careers_url": lookup_careers_url(key),
                "own_contacts": own,
                "marketplace_listings": market,
            }
        )

    # Sort by density descending, then alphabetically for ties
    results.sort(key=lambda r: (-r["network_density"], r["company_name"]))

    return results[:limit]


def _build_network_label(own: int, market: int) -> str:
    """Generate a human-readable network label from contact counts."""
    total = own + market
    suffix = "connection" if total == 1 else "connections"
    if own and market:
        return f"{total} {suffix} ({own} direct, {market} extended)"
    if own:
        return f"{own} {suffix} in your network"
    return f"{market} {suffix} in extended network"
