"""Suppression list service — opt-out registry for contact privacy.

Provides:
- check_suppression(): check if a person is on the suppression list
- add_to_suppression(): add a person and purge their data across all vaults
- purge_suppressed_person(): cascade-delete a suppressed person's data
- notify_affected_holders(): notify network holders when their contacts are removed
- rectify_contact_data(): propagate data corrections across vaults
"""

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.privacy import SuppressionList
from app.models.user import User
from app.services.audit_logger import log_event
from app.utils.encryption import compute_blind_index
from app.utils.hashing import hash_for_suppression

logger = logging.getLogger(__name__)


async def check_suppression(
    email: str | None,
    first_name: str,
    last_name: str,
    company: str,
    db: AsyncSession,
) -> bool:
    """Returns True if person is on the suppression list."""
    # Check email hash
    if email:
        email_hash = hash_for_suppression(email)
        result = await db.execute(
            select(SuppressionList.id).where(SuppressionList.email_hash == email_hash)
        )
        if result.scalar_one_or_none() is not None:
            return True

    # Check name+company hash
    name_company = f"{first_name}{last_name}{company}"
    name_company_hash = hash_for_suppression(name_company)
    result = await db.execute(
        select(SuppressionList.id).where(
            SuppressionList.name_company_hash == name_company_hash
        )
    )
    return result.scalar_one_or_none() is not None


async def add_to_suppression(
    email: str | None,
    first_name: str,
    last_name: str,
    company: str,
    reason: str,
    db: AsyncSession,
) -> uuid.UUID:
    """Add person to suppression list and trigger purge across all vaults."""
    email_hash = hash_for_suppression(email) if email else None
    name_company = f"{first_name}{last_name}{company}"
    name_company_hash = hash_for_suppression(name_company)

    entry = SuppressionList(
        email_hash=email_hash,
        name_company_hash=name_company_hash,
        reason=reason,
        requested_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()

    await log_event(
        db,
        "suppression_added",
        metadata={"reason": reason, "suppression_id": str(entry.id)},
    )

    # Compute blind indexes from plaintext for indexed lookups
    email_bi = compute_blind_index(email) if email else None
    name_company_bi = compute_blind_index(name_company)

    # Purge across all vaults
    await purge_suppressed_person(email_bi, name_company_bi, db)

    return entry.id


async def purge_suppressed_person(
    email_blind_index: str | None,
    name_company_blind_index: str | None,
    db: AsyncSession,
) -> int:
    """Remove person from ALL network holders' data.

    Uses blind-index columns for O(1) indexed lookups instead of full-table scans.

    - Find matching contacts across all users
    - Delete their marketplace_listings
    - Soft-delete the contacts themselves
    - Cancel any pending intro_facilitations

    Returns count of records affected.
    """
    affected = 0

    # Find matching contacts via blind indexes (indexed O(1) lookups)
    contact_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    if email_blind_index:
        result = await db.execute(
            select(Contact.id, Contact.user_id).where(
                Contact.email_blind_index == email_blind_index,
                Contact.deleted_at.is_(None),
            )
        )
        for row in result.all():
            if row[0] not in seen:
                contact_ids.append(row[0])
                seen.add(row[0])

    if name_company_blind_index:
        result = await db.execute(
            select(Contact.id, Contact.user_id).where(
                Contact.name_company_blind_index == name_company_blind_index,
                Contact.deleted_at.is_(None),
            )
        )
        for row in result.all():
            if row[0] not in seen:
                contact_ids.append(row[0])
                seen.add(row[0])

    if not contact_ids:
        return 0

    # Batch-load marketplace listings for all matched contacts
    listing_result = await db.execute(
        select(MarketplaceListing).where(
            MarketplaceListing.contact_id.in_(contact_ids),
            MarketplaceListing.deleted_at.is_(None),
        )
    )
    listings = list(listing_result.scalars())

    # Batch-cancel pending intro facilitations for all affected listings
    listing_ids = [l.id for l in listings]
    if listing_ids:
        await db.execute(
            update(IntroFacilitation)
            .where(
                IntroFacilitation.marketplace_listing_id.in_(listing_ids),
                IntroFacilitation.status.in_(["requested", "reviewing"]),
            )
            .values(status="expired")
        )

    now = datetime.now(timezone.utc)
    for listing in listings:
        listing.deleted_at = now
        affected += 1

    # Batch-load contacts for soft-delete
    contact_result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts = list(contact_result.scalars())

    affected_holder_ids: set[uuid.UUID] = set()
    for contact in contacts:
        if contact.deleted_at is None:
            affected_holder_ids.add(contact.user_id)
            contact.deleted_at = now
            affected += 1

    # Notify affected network holders
    if affected_holder_ids:
        await notify_affected_holders(affected_holder_ids, db)

    return affected


async def notify_affected_holders(
    holder_ids: set[uuid.UUID],
    db: AsyncSession,
) -> int:
    """Notify network holders that a contact was removed due to a privacy request.

    Does NOT reveal which contact or who requested removal.
    Returns count of notifications sent.
    """
    from app.services.email_service import _send_email

    # Batch-load all holder users
    users_result = await db.execute(select(User).where(User.id.in_(holder_ids)))
    users_map = {u.id: u for u in users_result.scalars()}

    count = 0
    for holder_id in holder_ids:
        user = users_map.get(holder_id)
        if user is None:
            continue

        _send_email(
            to=user.email,
            subject="A contact was removed from your WarmPath vault",
            html=(
                "<p>A contact in your WarmPath vault was removed due to a "
                "privacy request.</p>"
                "<p>This is part of our commitment to respecting individuals' "
                "privacy choices. No action is needed from you.</p>"
                "<p>For questions, contact us at rovik@majiq.agency.</p>"
            ),
        )

        await log_event(
            db,
            "suppression_holder_notified",
            user_id=holder_id,
            metadata={"reason": "contact_removed_privacy_request"},
        )
        count += 1

    return count


async def rectify_contact_data(
    email: str | None,
    first_name: str | None,
    last_name: str | None,
    company: str | None,
    corrections: dict,
    db: AsyncSession,
) -> int:
    """Propagate data corrections for a person across all vaults.

    Uses blind-index columns for O(1) indexed lookups instead of full-table scans.
    Finds matching contacts by email or name+company blind index, then applies
    the provided corrections dict (e.g. {"current_company": "New Corp"}).

    Returns count of contacts updated.
    """
    contact_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()

    # Find by email blind index
    if email:
        email_bi = compute_blind_index(email)
        result = await db.execute(
            select(Contact.id).where(
                Contact.email_blind_index == email_bi,
                Contact.deleted_at.is_(None),
            )
        )
        for row in result.all():
            if row[0] not in seen:
                contact_ids.append(row[0])
                seen.add(row[0])

    # Find by name+company blind index
    if first_name and last_name and company:
        name_company = f"{first_name}{last_name}{company}"
        nc_bi = compute_blind_index(name_company)
        result = await db.execute(
            select(Contact.id).where(
                Contact.name_company_blind_index == nc_bi,
                Contact.deleted_at.is_(None),
            )
        )
        for row in result.all():
            if row[0] not in seen:
                contact_ids.append(row[0])
                seen.add(row[0])

    if not contact_ids:
        return 0

    # Apply corrections
    allowed_fields = {
        "first_name",
        "last_name",
        "current_company",
        "current_title",
        "email",
        "location",
    }
    safe_corrections = {k: v for k, v in corrections.items() if k in allowed_fields}

    # Batch-load all contacts for rectification
    contacts_result = await db.execute(
        select(Contact).where(Contact.id.in_(contact_ids))
    )
    contacts_map = {c.id: c for c in contacts_result.scalars()}

    count = 0
    for cid in contact_ids:
        contact = contacts_map.get(cid)
        if contact is None:
            continue
        for field, value in safe_corrections.items():
            setattr(contact, field, value)
        count += 1

    await log_event(
        db,
        "contact_data_rectified",
        metadata={
            "contacts_updated": count,
            "fields_corrected": list(safe_corrections.keys()),
        },
    )
    await db.flush()
    return count
