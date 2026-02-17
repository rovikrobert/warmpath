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

    # Purge across all vaults
    await purge_suppressed_person(email_hash, name_company_hash, db)

    return entry.id


async def purge_suppressed_person(
    email_hash: str | None,
    name_company_hash: str | None,
    db: AsyncSession,
) -> int:
    """Remove person from ALL network holders' data.

    - Find matching contacts across all users
    - Delete their marketplace_listings
    - Soft-delete the contacts themselves
    - Cancel any pending intro_facilitations

    Returns count of records affected.
    """
    affected = 0

    # Find matching contacts by email or name+company fingerprint
    contact_ids: list[uuid.UUID] = []

    if email_hash:
        # We need to find contacts whose email hashes match.
        # Since contacts store plaintext emails, we load candidates and hash.
        result = await db.execute(
            select(Contact).where(
                Contact.email.isnot(None),
                Contact.deleted_at.is_(None),
            )
        )
        for contact in result.scalars():
            if hash_for_suppression(contact.email) == email_hash:
                contact_ids.append(contact.id)

    if name_company_hash:
        result = await db.execute(
            select(Contact).where(
                Contact.first_name.isnot(None),
                Contact.last_name.isnot(None),
                Contact.current_company.isnot(None),
                Contact.deleted_at.is_(None),
            )
        )
        for contact in result.scalars():
            name_company = (
                f"{contact.first_name}{contact.last_name}{contact.current_company}"
            )
            if hash_for_suppression(name_company) == name_company_hash:
                if contact.id not in contact_ids:
                    contact_ids.append(contact.id)

    if not contact_ids:
        return 0

    # Delete marketplace listings for these contacts
    for cid in contact_ids:
        listing_result = await db.execute(
            select(MarketplaceListing).where(
                MarketplaceListing.contact_id == cid,
                MarketplaceListing.deleted_at.is_(None),
            )
        )
        for listing in listing_result.scalars():
            # Cancel pending intro facilitations for this listing
            await db.execute(
                update(IntroFacilitation)
                .where(
                    IntroFacilitation.marketplace_listing_id == listing.id,
                    IntroFacilitation.status.in_(["requested", "reviewing"]),
                )
                .values(status="expired")
            )
            listing.deleted_at = datetime.now(timezone.utc)
            affected += 1

    # Collect affected user_ids for notification before soft-deleting
    affected_holder_ids: set[uuid.UUID] = set()

    # Soft-delete the contacts
    now = datetime.now(timezone.utc)
    for cid in contact_ids:
        result = await db.execute(select(Contact).where(Contact.id == cid))
        contact = result.scalar_one_or_none()
        if contact and contact.deleted_at is None:
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

    count = 0
    for holder_id in holder_ids:
        result = await db.execute(select(User).where(User.id == holder_id))
        user = result.scalar_one_or_none()
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

    Finds matching contacts by email or name+company hash, then applies
    the provided corrections dict (e.g. {"current_company": "New Corp"}).

    Returns count of contacts updated.
    """
    contact_ids: list[uuid.UUID] = []

    # Find by email
    if email:
        email_hash = hash_for_suppression(email)
        result = await db.execute(
            select(Contact).where(
                Contact.email.isnot(None),
                Contact.deleted_at.is_(None),
            )
        )
        for contact in result.scalars():
            if hash_for_suppression(contact.email) == email_hash:
                contact_ids.append(contact.id)

    # Find by name+company
    if first_name and last_name and company:
        name_company = f"{first_name}{last_name}{company}"
        name_company_hash = hash_for_suppression(name_company)
        result = await db.execute(
            select(Contact).where(
                Contact.first_name.isnot(None),
                Contact.last_name.isnot(None),
                Contact.current_company.isnot(None),
                Contact.deleted_at.is_(None),
            )
        )
        for contact in result.scalars():
            nc = f"{contact.first_name}{contact.last_name}{contact.current_company}"
            if hash_for_suppression(nc) == name_company_hash:
                if contact.id not in contact_ids:
                    contact_ids.append(contact.id)

    if not contact_ids:
        return 0

    # Apply corrections
    allowed_fields = {
        "first_name", "last_name", "current_company", "current_title",
        "email", "location",
    }
    safe_corrections = {k: v for k, v in corrections.items() if k in allowed_fields}

    count = 0
    for cid in contact_ids:
        result = await db.execute(select(Contact).where(Contact.id == cid))
        contact = result.scalar_one_or_none()
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
