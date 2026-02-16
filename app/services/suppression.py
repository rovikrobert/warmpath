"""Suppression list service — opt-out registry for contact privacy.

Provides:
- check_suppression(): check if a person is on the suppression list
- add_to_suppression(): add a person and purge their data across all vaults
- purge_suppressed_person(): cascade-delete a suppressed person's data
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.privacy import SuppressionList
from app.utils.hashing import hash_for_suppression


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
            select(SuppressionList.id).where(
                SuppressionList.email_hash == email_hash
            )
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

    # Soft-delete the contacts
    now = datetime.now(timezone.utc)
    for cid in contact_ids:
        result = await db.execute(select(Contact).where(Contact.id == cid))
        contact = result.scalar_one_or_none()
        if contact and contact.deleted_at is None:
            contact.deleted_at = now
            affected += 1

    return affected
