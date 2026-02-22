"""Feed API endpoints.

Surfaces the proactive engagement feed to the frontend.
The feed is the "inbound" experience the user asked for —
WarmPath doing work on their behalf and showing results.

Endpoints:
  GET  /feed           — paginated feed items (ranked by learned weights)
  GET  /feed/count     — unread count (for badge/notification dot)
  GET  /feed/stats     — admin/debug engagement stats per item type
  POST /feed/{id}/seen — mark item as seen
  POST /feed/{id}/act  — mark item as acted on (clicked through)
  POST /feed/{id}/dismiss — dismiss item
  POST /feed/dismiss-all — dismiss all visible feed items
  POST /feed/enrichment-response — submit enrichment prompt answer
  POST /feed/generate  — manual trigger for feed generation (dev/admin)
"""

import hashlib
import uuid
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.contact import Contact
from app.models.feed import ContactFreshnessSignal, FeedItem, FeedItemInteraction
from app.models.user import User
from app.services.credits import earn_credits
from app.services.feed_ranker import (
    compute_feed_stats,
    get_type_weights,
    rank_feed_items,
)
from app.utils.security import get_current_user
from app.utils.tracking import track_action

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class FeedItemResponse(BaseModel):
    id: str
    item_type: str
    title: str
    body: str | None
    icon: str | None
    action_url: str | None
    action_label: str | None
    priority: int
    metadata: dict | None
    seen_at: str | None
    acted_on_at: str | None
    created_at: str

    model_config = ConfigDict(from_attributes=True)


class FeedCountResponse(BaseModel):
    unseen: int
    total: int


class EnrichmentResponseRequest(BaseModel):
    feed_item_id: str
    signal_type: Literal["relationship_type", "would_refer", "recency"]
    signal_value: str  # e.g. "colleague", "definitely", "2026-01-15"  # {"type": "colleague"} or {"likelihood": "definitely"}


def _serialize_feed_item(item: FeedItem) -> dict:
    """Convert a FeedItem ORM object to API response dict."""
    return {
        "id": str(item.id),
        "item_type": item.item_type,
        "title": item.title,
        "body": item.body,
        "icon": item.icon,
        "action_url": item.action_url,
        "action_label": item.action_label,
        "priority": item.priority,
        "metadata": item.metadata_,
        "seen_at": item.seen_at.isoformat() if item.seen_at else None,
        "acted_on_at": (item.acted_on_at.isoformat() if item.acted_on_at else None),
        "created_at": item.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# GET /feed — paginated feed with learned ranking
# ---------------------------------------------------------------------------


@router.get("")
async def get_feed(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    item_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the user's activity feed, ranked by learned type weights.

    Unseen items appear first. Within each group, items are ranked by
    priority * type_weight * recency_boost (auto-tuned from interaction data).
    """
    await track_action(db, current_user.id, "feed_view")

    query = select(FeedItem).where(
        FeedItem.user_id == current_user.id,
        FeedItem.dismissed_at.is_(None),
    )

    # Filter expired items
    now = datetime.now(timezone.utc)
    query = query.where((FeedItem.expires_at.is_(None)) | (FeedItem.expires_at > now))

    if item_type:
        query = query.where(FeedItem.item_type == item_type)

    # Fetch all matching items (ranking happens in Python via learned weights)
    result = await db.execute(query)
    all_items = list(result.scalars().all())

    # Split unseen / seen, rank each group independently, then concatenate
    unseen = [i for i in all_items if i.seen_at is None]
    seen = [i for i in all_items if i.seen_at is not None]

    type_weights = await get_type_weights(db)
    ranked = rank_feed_items(unseen, type_weights) + rank_feed_items(seen, type_weights)

    # Apply pagination
    page = ranked[offset : offset + limit]

    await db.commit()

    return {
        "data": [_serialize_feed_item(item) for item in page],
        "meta": {"offset": offset, "limit": limit, "count": len(page)},
    }


# ---------------------------------------------------------------------------
# GET /feed/count — unread badge
# ---------------------------------------------------------------------------


@router.get("/count")
async def get_feed_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get unseen and total feed item counts for notification badge."""
    now = datetime.now(timezone.utc)

    unseen_result = await db.execute(
        select(func.count(FeedItem.id)).where(
            FeedItem.user_id == current_user.id,
            FeedItem.seen_at.is_(None),
            FeedItem.dismissed_at.is_(None),
            (FeedItem.expires_at.is_(None)) | (FeedItem.expires_at > now),
        )
    )
    unseen = unseen_result.scalar_one()

    total_result = await db.execute(
        select(func.count(FeedItem.id)).where(
            FeedItem.user_id == current_user.id,
            FeedItem.dismissed_at.is_(None),
            (FeedItem.expires_at.is_(None)) | (FeedItem.expires_at > now),
        )
    )
    total = total_result.scalar_one()

    return {"data": {"unseen": unseen, "total": total}, "meta": {}}


# ---------------------------------------------------------------------------
# GET /feed/stats — admin/debug engagement stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def get_feed_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return feed engagement statistics for debugging and tuning.

    Per-type: generated_count, seen_count, act_count, dismiss_count,
    engagement_score, current_weight.
    Overall: total_items, avg_engagement, most/least engaging types.
    Time series: daily engagement scores for last 14 days.
    """
    stats = await compute_feed_stats(db)
    return {"data": stats, "meta": {}}


# ---------------------------------------------------------------------------
# POST /feed/{id}/seen — mark as seen
# ---------------------------------------------------------------------------


@router.post("/{item_id}/seen")
async def mark_seen(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a feed item as seen. Also logs a 'view' interaction."""
    result = await db.execute(
        select(FeedItem).where(
            FeedItem.id == item_id,
            FeedItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feed item not found")

    now = datetime.now(timezone.utc)
    if not item.seen_at:
        item.seen_at = now

    # Log interaction
    db.add(
        FeedItemInteraction(
            feed_item_id=item.id,
            user_id=current_user.id,
            interaction_type="view",
            source="in_app",
        )
    )

    await db.commit()
    return {"data": {"status": "seen"}, "meta": {}}


# ---------------------------------------------------------------------------
# POST /feed/{id}/act — mark as acted on
# ---------------------------------------------------------------------------


@router.post("/{item_id}/act")
async def mark_acted(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a feed item as acted on (user clicked through to action)."""
    result = await db.execute(
        select(FeedItem).where(
            FeedItem.id == item_id,
            FeedItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feed item not found")

    now = datetime.now(timezone.utc)
    if not item.seen_at:
        item.seen_at = now
    item.acted_on_at = now

    db.add(
        FeedItemInteraction(
            feed_item_id=item.id,
            user_id=current_user.id,
            interaction_type="click",
            source="in_app",
        )
    )

    await track_action(
        db,
        current_user.id,
        "feed_item_click",
        resource_id=item.id,
        metadata_={"item_type": item.item_type},
    )

    await db.commit()
    return {"data": {"status": "acted"}, "meta": {}}


# ---------------------------------------------------------------------------
# POST /feed/{id}/dismiss — dismiss item
# ---------------------------------------------------------------------------


@router.post("/{item_id}/dismiss")
async def dismiss_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss a feed item (won't appear again)."""
    result = await db.execute(
        select(FeedItem).where(
            FeedItem.id == item_id,
            FeedItem.user_id == current_user.id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feed item not found")

    item.dismissed_at = datetime.now(timezone.utc)

    db.add(
        FeedItemInteraction(
            feed_item_id=item.id,
            user_id=current_user.id,
            interaction_type="dismiss",
            source="in_app",
        )
    )

    await db.commit()
    return {"data": {"status": "dismissed"}, "meta": {}}


# ---------------------------------------------------------------------------
# POST /feed/dismiss-all — bulk dismiss all visible feed items
# ---------------------------------------------------------------------------


@router.post("/dismiss-all")
async def dismiss_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dismiss all non-dismissed feed items for the current user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        update(FeedItem)
        .where(
            FeedItem.user_id == current_user.id,
            FeedItem.dismissed_at.is_(None),
        )
        .values(dismissed_at=now)
        .returning(FeedItem.id)
    )
    dismissed_ids = [row[0] for row in result.fetchall()]

    if dismissed_ids:
        db.add_all(
            [
                FeedItemInteraction(
                    feed_item_id=fid,
                    user_id=current_user.id,
                    interaction_type="dismiss",
                    source="in_app",
                )
                for fid in dismissed_ids
            ]
        )

    await db.commit()
    return {"data": {"dismissed": len(dismissed_ids)}, "meta": {}}


# ---------------------------------------------------------------------------
# POST /feed/enrichment-response — submit enrichment answer
# ---------------------------------------------------------------------------


_SIGNAL_KEY_MAP = {
    "relationship_type": "type",
    "would_refer": "likelihood",
    "recency": "recency",
}

# API uses "recency" but DB CHECK constraint expects "last_interaction"
_SIGNAL_TYPE_TO_DB = {
    "relationship_type": "relationship_type",
    "would_refer": "would_refer",
    "recency": "last_interaction",
}


def _build_signal_value(signal_type: str, signal_value: str) -> dict:
    """Convert flat signal_value string to typed dict for JSONB storage."""
    key = _SIGNAL_KEY_MAP.get(signal_type, "value")
    return {key: signal_value}


def _apply_signal_to_contact(
    contact: "Contact", signal_type: str, signal_value: str
) -> None:
    """Write enrichment signal back to the contact record."""
    if signal_type == "relationship_type":
        contact.relationship_type = signal_value
    elif signal_type == "would_refer":
        contact.would_refer = signal_value
    elif signal_type == "recency":
        contact.last_interaction_date = date.fromisoformat(signal_value)


@router.post("/enrichment-response")
async def submit_enrichment_response(
    payload: EnrichmentResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit an answer to an enrichment prompt (e.g. relationship type).

    This is the key data collection endpoint — every response enriches the
    trust graph and improves match quality. The signal is stored in
    contact_freshness_signals and applied back to the contact record.
    Awards 5 credits per enrichment response.
    """
    feed_item_id = uuid.UUID(payload.feed_item_id)

    # Verify feed item belongs to user
    item_result = await db.execute(
        select(FeedItem).where(
            FeedItem.id == feed_item_id,
            FeedItem.user_id == current_user.id,
        )
    )
    item = item_result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Feed item not found")

    # Extract contact_id from feed item metadata
    metadata = item.metadata_ or {}
    raw_contact_id = metadata.get("contact_id")
    if not raw_contact_id:
        raise HTTPException(
            status_code=400, detail="Feed item has no associated contact"
        )
    contact_id = uuid.UUID(raw_contact_id)

    # Verify contact belongs to user
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Build privacy-safe cross-user hash
    name_company = (
        f"{(contact.full_name or '').lower()}|{(contact.current_company or '').lower()}"
    )
    name_company_hash = hashlib.sha256(name_company.encode()).hexdigest()

    # Build signal_value dict for storage
    signal_value_dict = _build_signal_value(payload.signal_type, payload.signal_value)
    db_signal_type = _SIGNAL_TYPE_TO_DB[payload.signal_type]

    # Upsert freshness signal (one per user + contact + signal_type)
    existing_signal_result = await db.execute(
        select(ContactFreshnessSignal).where(
            ContactFreshnessSignal.user_id == current_user.id,
            ContactFreshnessSignal.contact_id == contact_id,
            ContactFreshnessSignal.signal_type == db_signal_type,
        )
    )
    existing_signal = existing_signal_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if existing_signal:
        existing_signal.signal_value = signal_value_dict
        existing_signal.name_company_hash = name_company_hash
        existing_signal.source = "feed_prompt"
        signal = existing_signal
    else:
        signal = ContactFreshnessSignal(
            user_id=current_user.id,
            contact_id=contact_id,
            signal_type=db_signal_type,
            signal_value=signal_value_dict,
            name_company_hash=name_company_hash,
            source="feed_prompt",
        )
        db.add(signal)

    # Apply signal to contact record
    _apply_signal_to_contact(contact, payload.signal_type, payload.signal_value)
    signal.applied_at = now

    # Mark feed item as acted on
    if not item.seen_at:
        item.seen_at = now
    item.acted_on_at = now

    db.add(
        FeedItemInteraction(
            feed_item_id=item.id,
            user_id=current_user.id,
            interaction_type="click",
            source="in_app",
            metadata_={"signal_type": payload.signal_type},
        )
    )

    # Flush pending objects (signal + interaction) before earn_credits,
    # which runs a SELECT that triggers autoflush. Without this, the
    # autoflush can fail on CHECK constraints mid-query.
    await db.flush()

    # Award 5 credits for enrichment response
    await earn_credits(
        current_user.id,
        5,
        "enrichment_response",
        db,
        reference_id=contact_id,
    )

    await track_action(
        db,
        current_user.id,
        "enrichment_response",
        resource_id=contact_id,
        metadata_={
            "signal_type": payload.signal_type,
            "signal_value": payload.signal_value,
        },
    )

    # Check if a milestone was crossed
    from app.services.enrichment_progress import check_and_award_milestones

    milestone_reached = await check_and_award_milestones(current_user.id, db)

    await db.commit()

    return {
        "data": {
            "status": "recorded",
            "signal_type": payload.signal_type,
            "applied": True,
            "credits_awarded": 5,
            "milestone_reached": milestone_reached,
            "contact": {
                "id": str(contact.id),
                "full_name": contact.full_name,
                "current_company": contact.current_company,
                "current_title": contact.current_title,
                "relationship_type": contact.relationship_type,
                "would_refer": contact.would_refer,
                "last_interaction_date": (
                    contact.last_interaction_date.isoformat()
                    if contact.last_interaction_date
                    else None
                ),
            },
        },
        "meta": {},
    }


# ---------------------------------------------------------------------------
# POST /feed/generate — manual trigger (dev/admin)
# ---------------------------------------------------------------------------


@router.post("/generate")
async def trigger_feed_generation(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manually trigger feed generation for the current user.

    Useful for dev/testing. In production, feed generation runs via Celery Beat.
    """
    from app.services.feed_generator import generate_feed_for_user

    items = await generate_feed_for_user(current_user.id, db)
    await db.commit()

    return {
        "data": {
            "items_generated": len(items),
            "item_types": [i.item_type for i in items],
        },
        "meta": {},
    }


# ---------------------------------------------------------------------------
# POST /feed/batch-seen — mark multiple items as seen at once
# ---------------------------------------------------------------------------


class BatchSeenRequest(BaseModel):
    item_ids: list[str]


@router.post("/batch-seen")
async def batch_mark_seen(
    payload: BatchSeenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark multiple feed items as seen (called when feed scrolls into view)."""
    now = datetime.now(timezone.utc)
    item_uuids = [uuid.UUID(i) for i in payload.item_ids]

    await db.execute(
        update(FeedItem)
        .where(
            FeedItem.id.in_(item_uuids),
            FeedItem.user_id == current_user.id,
            FeedItem.seen_at.is_(None),
        )
        .values(seen_at=now)
    )

    await db.commit()
    return {"data": {"marked": len(item_uuids)}, "meta": {}}
