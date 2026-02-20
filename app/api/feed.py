"""Feed API endpoints.

Surfaces the proactive engagement feed to the frontend.
The feed is the "inbound" experience the user asked for —
WarmPath doing work on their behalf and showing results.

Endpoints:
  GET  /feed           — paginated feed items (unseen first, then seen)
  GET  /feed/count     — unread count (for badge/notification dot)
  POST /feed/{id}/seen — mark item as seen
  POST /feed/{id}/act  — mark item as acted on (clicked through)
  POST /feed/{id}/dismiss — dismiss item
  POST /feed/enrichment-response — submit enrichment prompt answer
  POST /feed/generate  — manual trigger for feed generation (dev/admin)
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.feed import ContactFreshnessSignal, FeedItem, FeedItemInteraction
from app.models.user import User
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
    contact_id: str
    signal_type: str  # relationship_type, would_refer, etc.
    signal_value: dict  # {"type": "colleague"} or {"likelihood": "definitely"}


# ---------------------------------------------------------------------------
# GET /feed — paginated feed
# ---------------------------------------------------------------------------


@router.get("")
async def get_feed(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    item_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the user's activity feed, ordered by priority and recency.

    Unseen items appear first (sorted by priority desc, created_at desc),
    followed by seen items.
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

    # Order: unseen first (seen_at IS NULL), then by priority and recency
    query = (
        query.order_by(
            FeedItem.seen_at.is_(None).desc(),  # NULL (unseen) sorts first
            FeedItem.priority.desc(),
            FeedItem.created_at.desc(),
        )
        .offset(offset)
        .limit(limit)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    # Build response
    feed_items = []
    for item in items:
        feed_items.append(
            {
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
                "acted_on_at": (
                    item.acted_on_at.isoformat() if item.acted_on_at else None
                ),
                "created_at": item.created_at.isoformat(),
            }
        )

    await db.commit()

    return {
        "data": feed_items,
        "meta": {"offset": offset, "limit": limit, "count": len(feed_items)},
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
# POST /feed/enrichment-response — submit enrichment answer
# ---------------------------------------------------------------------------


@router.post("/enrichment-response")
async def submit_enrichment_response(
    payload: EnrichmentResponseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit an answer to an enrichment prompt (e.g. relationship type).

    This is the key data collection endpoint — every response enriches the
    trust graph and improves match quality. The signal is stored in
    contact_freshness_signals and optionally applied back to the contact.
    """
    contact_id = uuid.UUID(payload.contact_id)
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

    # Verify contact belongs to user
    from app.models.contact import Contact

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
    import hashlib

    name_company = (
        f"{(contact.full_name or '').lower()}|{(contact.current_company or '').lower()}"
    )
    name_company_hash = hashlib.sha256(name_company.encode()).hexdigest()

    # Create freshness signal
    signal = ContactFreshnessSignal(
        user_id=current_user.id,
        contact_id=contact_id,
        signal_type=payload.signal_type,
        signal_value=payload.signal_value,
        name_company_hash=name_company_hash,
        source="feed_prompt",
    )
    db.add(signal)

    # Apply signal to contact if it's a relationship type
    if payload.signal_type == "relationship_type" and "type" in payload.signal_value:
        contact.relationship_type = payload.signal_value["type"]
        signal.applied_at = datetime.now(timezone.utc)

    # Mark feed item as acted on
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
            metadata_={"signal_type": payload.signal_type},
        )
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

    await db.commit()

    return {
        "data": {
            "status": "recorded",
            "signal_type": payload.signal_type,
            "applied": signal.applied_at is not None,
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
