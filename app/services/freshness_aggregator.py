"""Cross-user contact freshness signal aggregation.

Aggregates ContactFreshnessSignal records by name_company_hash to find
consensus. When enough users agree on a signal value, propagates it to
contacts with NULL fields. Company-change signals generate feed items
instead of direct updates.

Privacy: all aggregation uses hashed identifiers. The propagation log
stores NO user_ids — only hash, signal type, and aggregate counts.
"""

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.feed import (
    ContactFreshnessSignal,
    FeedItem,
    FreshnessPropagationLog,
)

logger = logging.getLogger(__name__)

FRESHNESS_CONSENSUS_THRESHOLD = 2

_DIRECT_PROPAGATION = {
    "relationship_type": ("type", "relationship_type"),
    "would_refer": ("likelihood", "would_refer"),
}

_COMPANY_CHANGE_SIGNALS = {"contact_moved", "still_at_company"}


def _dedup_key(name_company_hash: str, signal_type: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    raw = f"freshness_agg:{name_company_hash}:{signal_type}:{today}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


@dataclass
class AggregationResult:
    signals_processed: int = 0
    contacts_updated: int = 0
    feed_items_created: int = 0
    propagation_logs: int = 0


async def aggregate_freshness_signals(
    db: AsyncSession,
    threshold: int = FRESHNESS_CONSENSUS_THRESHOLD,
) -> AggregationResult:
    """Aggregate freshness signals and propagate consensus to contacts.

    Finds signal groups where >= threshold distinct users agree on a value,
    then either updates NULL contact fields (relationship_type, would_refer)
    or creates feed items (company changes).

    Returns an AggregationResult with counts of what was processed.
    """
    result = AggregationResult()
    consensus_groups = await _find_consensus_groups(db, threshold)
    result.signals_processed = len(consensus_groups)

    for group in consensus_groups:
        nch = group["name_company_hash"]
        signal_type = group["signal_type"]
        signal_value = group["signal_value"]
        source_count = group["source_count"]
        reporting_user_ids = group["reporting_user_ids"]

        if await _already_propagated_today(db, nch, signal_type):
            continue

        if signal_type in _DIRECT_PROPAGATION:
            updated = await _propagate_direct(
                db, nch, signal_type, signal_value, source_count
            )
            result.contacts_updated += updated
            result.propagation_logs += 1
        elif signal_type in _COMPANY_CHANGE_SIGNALS:
            if _is_company_change(signal_type, signal_value):
                created = await _create_company_change_feed_items(
                    db,
                    nch,
                    signal_type,
                    signal_value,
                    source_count,
                    reporting_user_ids,
                )
                result.feed_items_created += created
                result.propagation_logs += 1

    return result


async def _find_consensus_groups(db: AsyncSession, threshold: int) -> list[dict]:
    """Find signal groups where >= threshold distinct users agree."""
    signals_result = await db.execute(
        select(
            ContactFreshnessSignal.name_company_hash,
            ContactFreshnessSignal.signal_type,
            ContactFreshnessSignal.signal_value,
            ContactFreshnessSignal.user_id,
        ).where(
            ContactFreshnessSignal.name_company_hash.isnot(None),
        )
    )
    all_signals = signals_result.all()

    groups: dict[tuple, set[uuid.UUID]] = defaultdict(set)
    for row in all_signals:
        nch, stype, sval, uid = row
        canonical = json.dumps(sval, sort_keys=True)
        groups[(nch, stype, canonical)].add(uid)

    consensus = []
    for (nch, stype, canonical), user_ids in groups.items():
        if len(user_ids) >= threshold:
            consensus.append(
                {
                    "name_company_hash": nch,
                    "signal_type": stype,
                    "signal_value": json.loads(canonical),
                    "source_count": len(user_ids),
                    "reporting_user_ids": user_ids,
                }
            )

    return consensus


async def _already_propagated_today(
    db: AsyncSession, name_company_hash: str, signal_type: str
) -> bool:
    """Check if we already propagated this signal today (idempotency)."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    result = await db.execute(
        select(func.count(FreshnessPropagationLog.id)).where(
            FreshnessPropagationLog.name_company_hash == name_company_hash,
            FreshnessPropagationLog.signal_type == signal_type,
            FreshnessPropagationLog.created_at >= today_start,
        )
    )
    return result.scalar_one() > 0


async def _propagate_direct(
    db: AsyncSession,
    name_company_hash: str,
    signal_type: str,
    signal_value: dict,
    source_count: int,
) -> int:
    """Propagate a consensus value to contacts with NULL fields."""
    value_key, contact_field = _DIRECT_PROPAGATION[signal_type]
    consensus_val = signal_value.get(value_key)
    if not consensus_val:
        return 0

    contacts_result = await db.execute(
        select(Contact).where(
            Contact.name_company_blind_index == name_company_hash,
            Contact.deleted_at.is_(None),
            getattr(Contact, contact_field).is_(None),
        )
    )
    contacts = contacts_result.scalars().all()

    for contact in contacts:
        setattr(contact, contact_field, consensus_val)

    log = FreshnessPropagationLog(
        name_company_hash=name_company_hash,
        signal_type=signal_type,
        consensus_value=signal_value,
        source_count=source_count,
        contacts_updated=len(contacts),
    )
    db.add(log)

    if contacts:
        logger.info(
            "Propagated %s consensus to %d contacts (hash=%s...)",
            signal_type,
            len(contacts),
            name_company_hash[:8],
        )

    return len(contacts)


def _is_company_change(signal_type: str, signal_value: dict) -> bool:
    """Determine if a signal represents a company change."""
    if signal_type == "contact_moved":
        return True
    if signal_type == "still_at_company":
        return signal_value.get("confirmed") is False
    return False


async def _create_company_change_feed_items(
    db: AsyncSession,
    name_company_hash: str,
    signal_type: str,
    signal_value: dict,
    source_count: int,
    reporting_user_ids: set[uuid.UUID],
) -> int:
    """Create feed items for users who didn't report the company change."""
    contacts_result = await db.execute(
        select(Contact).where(
            Contact.name_company_blind_index == name_company_hash,
            Contact.deleted_at.is_(None),
        )
    )
    contacts = contacts_result.scalars().all()
    target_contacts = [c for c in contacts if c.user_id not in reporting_user_ids]

    dedup = _dedup_key(name_company_hash, signal_type)
    created = 0

    if signal_type == "contact_moved":
        old_co = signal_value.get("old_company", "their company")
        new_co = signal_value.get("new_company", "a new company")
        title = f"Multiple sources suggest a contact may have left {old_co}"
        body = (
            f"{source_count} people in the network report this contact "
            f"may have moved to {new_co}."
        )
    else:
        title = "Multiple sources suggest a contact may have changed companies"
        body = (
            f"{source_count} people in the network report this contact "
            f"may no longer be at their listed company."
        )

    total_contacts = len(contacts)
    stale_confidence = round(source_count / max(total_contacts, 1), 2)

    for contact in target_contacts:
        existing = await db.execute(
            select(func.count(FeedItem.id)).where(
                FeedItem.user_id == contact.user_id,
                FeedItem.dedup_key == dedup,
                FeedItem.dismissed_at.is_(None),
            )
        )
        if existing.scalar_one() > 0:
            continue

        item = FeedItem(
            user_id=contact.user_id,
            item_type="contact_update",
            title=title,
            body=body,
            icon="alert-circle",
            action_url=f"/contacts?highlight={contact.id}",
            action_label="Review contact",
            priority=65,
            dedup_key=dedup,
            metadata_={
                "contact_id": str(contact.id),
                "signal_type": signal_type,
                "consensus_count": source_count,
                "total_sources": total_contacts,
                "stale_confidence": stale_confidence,
            },
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        db.add(item)
        created += 1

    log = FreshnessPropagationLog(
        name_company_hash=name_company_hash,
        signal_type=signal_type,
        consensus_value=signal_value,
        source_count=source_count,
        contacts_updated=0,
    )
    db.add(log)

    if created:
        logger.info(
            "Created %d company-change feed items (hash=%s...)",
            created,
            name_company_hash[:8],
        )

    return created
