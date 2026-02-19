"""Marketplace indexer — generates anonymized listings from contacts.

Called when a network holder opts into marketplace sharing. Reads their
contacts, checks sharing preferences (category filters, exclusions),
checks the suppression list, and creates anonymized MarketplaceListing rows.
"""

import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.contact import Contact
from app.models.marketplace import MarketplaceListing, NetworkSharingPreferences
from app.models.match_result import WarmScore
from app.models.privacy import SuppressionList
from app.utils.hashing import hash_for_suppression


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------

# Role level keywords (checked in priority order)
_VP_PATTERNS = re.compile(r"\b(vp|vice president)\b", re.IGNORECASE)
_CSUITE_PATTERNS = re.compile(r"\b(ceo|cto|cfo|coo|cmo|cpo|chief)\b", re.IGNORECASE)
_DIRECTOR_PATTERNS = re.compile(r"\b(director)\b", re.IGNORECASE)
_LEAD_PATTERNS = re.compile(r"\b(lead|principal|staff|head of)\b", re.IGNORECASE)
_SENIOR_PATTERNS = re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)
_JUNIOR_PATTERNS = re.compile(
    r"\b(junior|jr\.?|intern|trainee|associate|entry)\b", re.IGNORECASE
)


def classify_role_level(position: str | None) -> str:
    """Classify a job title into a role level enum.

    Returns one of: junior, mid, senior, lead, director, vp, c_suite
    """
    if not position:
        return "mid"

    if _CSUITE_PATTERNS.search(position):
        return "c_suite"
    if _VP_PATTERNS.search(position):
        return "vp"
    if _DIRECTOR_PATTERNS.search(position):
        return "director"
    if _LEAD_PATTERNS.search(position):
        return "lead"
    if _SENIOR_PATTERNS.search(position):
        return "senior"
    if _JUNIOR_PATTERNS.search(position):
        return "junior"
    return "mid"


# Department classification patterns
_DEPT_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        "engineering",
        re.compile(
            r"\b(engineer\w*|developer|software|sre|devops|backend|frontend|"
            r"full.?stack|data scientist|machine learning|ml|ai|architect)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "product",
        re.compile(
            r"\b(product manager|product lead|product owner|pm)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "design",
        re.compile(
            r"\b(design|ux|ui|creative|brand)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "marketing",
        re.compile(
            r"\b(marketing|growth|content|seo|sem|brand|communications)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "sales",
        re.compile(
            r"\b(sales|account executive|business development|bdr|sdr|"
            r"account manager|revenue)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "ops",
        re.compile(
            r"\b(operations|ops|supply chain|logistics|procurement)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "finance",
        re.compile(
            r"\b(finance|accounting|controller|treasury|fp&a|cfo)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "hr",
        re.compile(
            r"\b(human resources|hr|people|talent|recruiting|recruiter)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "legal",
        re.compile(
            r"\b(legal|counsel|compliance|attorney|lawyer)\b",
            re.IGNORECASE,
        ),
    ),
]


def classify_department(position: str | None) -> str:
    """Classify a job title into a department category.

    Returns one of: engineering, product, design, marketing, sales,
    ops, finance, hr, legal, other
    """
    if not position:
        return "other"

    for dept, pattern in _DEPT_PATTERNS:
        if pattern.search(position):
            return dept
    return "other"


def classify_warm_score_range(score: float | None) -> str:
    """Derive warm_score_range from numeric warm score.

    >70 = high, 40-70 = medium, <40 = low
    """
    if score is None:
        return "low"
    if score > 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def classify_connection_recency(connected_on: date | None) -> str:
    """Derive connection_recency from connected_on date.

    <1yr = recent, 1-3yr = moderate, >3yr = stale
    """
    if connected_on is None:
        return "stale"
    today = date.today()
    days = (today - connected_on).days
    if days < 365:
        return "recent"
    if days < 365 * 3:
        return "moderate"
    return "stale"


# ---------------------------------------------------------------------------
# Contact eligibility check
# ---------------------------------------------------------------------------


def _should_list_contact(
    contact: Contact,
    excluded_ids: list[str],
    exclude_companies: list[str],
    include_departments: list[str],
    suppressed_email_hashes: set[str],
    suppressed_name_co_hashes: set[str],
) -> bool:
    """Return True if a contact passes all marketplace listing filters."""
    if str(contact.id) in excluded_ids:
        return False

    if contact.company_id and str(contact.company_id) in exclude_companies:
        return False

    dept = classify_department(contact.current_title)
    if include_departments and dept not in include_departments:
        return False

    # Suppression list check (in-memory)
    if contact.email:
        if hash_for_suppression(contact.email) in suppressed_email_hashes:
            return False
    name_company = (
        f"{contact.first_name or ''}"
        f"{contact.last_name or ''}"
        f"{contact.current_company or ''}"
    )
    if hash_for_suppression(name_company) in suppressed_name_co_hashes:
        return False

    return True


# ---------------------------------------------------------------------------
# Main indexer
# ---------------------------------------------------------------------------


async def generate_marketplace_listings(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> int:
    """Generate anonymized marketplace listings for a network holder.

    Steps:
    1. Load user's NetworkSharingPreferences
    2. Load user's contacts with company + warm_score data
    3. For each contact: check suppression, exclusions, category filters
    4. If passes all checks -> create MarketplaceListing

    Returns count of listings created.
    """
    # 1. Load sharing preferences
    result = await db.execute(
        select(NetworkSharingPreferences).where(
            NetworkSharingPreferences.user_id == user_id
        )
    )
    prefs = result.scalar_one_or_none()
    if prefs is None or not prefs.opt_in_marketplace or prefs.is_paused:
        return 0

    excluded_ids: list[str] = prefs.excluded_contact_ids or []
    category_filters: dict = prefs.category_filters or {}
    include_departments: list[str] = category_filters.get("include_departments", [])
    exclude_companies: list[str] = category_filters.get("exclude_companies", [])

    # 2. Load contacts (not deleted, with company linked)
    result = await db.execute(
        select(Contact)
        .where(
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
            Contact.company_id.isnot(None),
        )
        .options(selectinload(Contact.company))
    )
    contacts = list(result.scalars())

    # Load warm scores for these contacts
    score_map: dict[uuid.UUID, float] = {}
    if contacts:
        ws_result = await db.execute(
            select(WarmScore).where(
                WarmScore.user_id == user_id,
                WarmScore.contact_id.in_([c.id for c in contacts]),
            )
        )
        for ws in ws_result.scalars():
            score_map[ws.contact_id] = float(ws.total_score)

    # Remove existing listings for this user (regenerate fresh)
    existing_result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.network_holder_id == user_id,
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    for listing in existing_result.scalars():
        listing.deleted_at = datetime.now(timezone.utc)

    # Batch-load ALL suppression hashes (avoids 1 query per contact)
    suppression_result = await db.execute(
        select(SuppressionList.email_hash, SuppressionList.name_company_hash)
    )
    suppressed_email_hashes: set[str] = set()
    suppressed_name_co_hashes: set[str] = set()
    for row in suppression_result.all():
        if row[0]:
            suppressed_email_hashes.add(row[0])
        if row[1]:
            suppressed_name_co_hashes.add(row[1])

    created = 0

    for contact in contacts:
        if not _should_list_contact(
            contact, excluded_ids, exclude_companies,
            include_departments, suppressed_email_hashes, suppressed_name_co_hashes,
        ):
            continue

        dept = classify_department(contact.current_title)

        # Create anonymized listing
        listing = MarketplaceListing(
            network_holder_id=user_id,
            contact_id=contact.id,
            company_id=contact.company_id,
            role_level=classify_role_level(contact.current_title),
            department_category=dept,
            warm_score_range=classify_warm_score_range(score_map.get(contact.id)),
            connection_recency=classify_connection_recency(contact.connected_on),
        )
        db.add(listing)
        created += 1

    await db.flush()
    return created
