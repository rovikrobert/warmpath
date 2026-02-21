"""Clerk webhook handler — syncs user lifecycle events to the database."""

import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.privacy import SuppressionList
from app.models.user import User
from app.services.audit_logger import log_event
from app.services.credits import earn_credits
from app.services.data_retention import archive_credit_history

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_webhook(request_body: bytes, headers: dict) -> dict:
    """Verify Clerk webhook signature using Svix, return parsed payload."""
    from svix.webhooks import Webhook, WebhookVerificationError

    if not settings.CLERK_WEBHOOK_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured",
        )

    wh = Webhook(settings.CLERK_WEBHOOK_SECRET)
    try:
        return wh.verify(request_body, headers)
    except WebhookVerificationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        ) from None


def _extract_primary_email(data: dict) -> tuple[str, bool]:
    """Extract primary email and verification status from Clerk user data."""
    email_addresses = data.get("email_addresses", [])
    if not email_addresses:
        return "", False
    first = email_addresses[0]
    email = first.get("email_address", "")
    verified = first.get("verification", {}).get("status") == "verified"
    return email, verified


def _extract_full_name(data: dict) -> str:
    """Build full name from Clerk's first_name + last_name."""
    parts = [data.get("first_name", ""), data.get("last_name", "")]
    return " ".join(p for p in parts if p).strip() or "User"


@router.post("/webhooks/clerk")
async def clerk_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle Clerk webhook events (user.created, user.updated, user.deleted)."""
    body = await request.body()
    headers = dict(request.headers)

    # Allow test bypass (only in test/mock environment)
    if headers.get("x-webhook-test") == "true" and settings.AI_MOCK_MODE:
        payload = json.loads(body)
    else:
        payload = _verify_webhook(body, headers)

    event_type = payload.get("type", "")
    data = payload.get("data", {})
    clerk_user_id = data.get("id", "")

    if event_type == "user.created":
        await _handle_user_created(clerk_user_id, data, db)
    elif event_type == "user.updated":
        await _handle_user_updated(clerk_user_id, data, db)
    elif event_type == "user.deleted":
        await _handle_user_deleted(clerk_user_id, db)
    else:
        logger.info("Ignoring Clerk event: %s", event_type)

    return {"data": {"received": True}, "meta": {}}


async def _handle_user_created(
    clerk_user_id: str, data: dict, db: AsyncSession
) -> None:
    """Create a user row from Clerk user.created event."""
    # Idempotency: skip if user already exists
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    if result.scalar_one_or_none() is not None:
        logger.info("User %s already exists, skipping", clerk_user_id)
        return

    email, email_verified = _extract_primary_email(data)
    full_name = _extract_full_name(data)

    user = User(
        email=email,
        full_name=full_name,
        clerk_user_id=clerk_user_id,
        email_verified=email_verified,
    )
    db.add(user)
    await db.flush()

    # Award welcome bonus (skip if email was previously deleted / on suppression list)
    email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    suppression_result = await db.execute(
        select(SuppressionList).where(
            SuppressionList.email_hash == email_hash,
            SuppressionList.reason == "account_deleted",
        )
    )
    if suppression_result.scalars().first() is None:
        bonus = 500 if settings.BETA_SANDBOX_MODE else 50
        await earn_credits(user.id, bonus, "welcome_bonus", db)

    # Send welcome email
    from app.services.email_engagement import send_welcome_email_js

    await send_welcome_email_js(user, db)

    # Track signup funnel
    from app.utils.tracking import track_action

    await track_action(db, user.id, "signup")

    await db.commit()
    logger.info("Created user %s from Clerk webhook", clerk_user_id)


async def _handle_user_updated(
    clerk_user_id: str, data: dict, db: AsyncSession
) -> None:
    """Sync email, name, and verification status from Clerk."""
    result = await db.execute(
        select(User).where(
            User.clerk_user_id == clerk_user_id,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        logger.warning("user.updated for unknown clerk_id: %s", clerk_user_id)
        return

    email, email_verified = _extract_primary_email(data)
    full_name = _extract_full_name(data)

    # Detect email verification state transition (unverified → verified)
    newly_verified = email_verified and not user.email_verified

    if email:
        user.email = email
    user.full_name = full_name
    user.email_verified = email_verified

    if newly_verified:
        from app.utils.tracking import track_action

        await track_action(db, user.id, "email_verified")

    await db.commit()
    logger.info("Updated user %s from Clerk webhook", clerk_user_id)


async def _handle_user_deleted(clerk_user_id: str, db: AsyncSession) -> None:
    """Delete user and cascade from Clerk user.deleted event."""
    result = await db.execute(select(User).where(User.clerk_user_id == clerk_user_id))
    user = result.scalar_one_or_none()
    if user is None:
        logger.info("user.deleted for unknown clerk_id: %s", clerk_user_id)
        return

    user_id = user.id
    user_email = user.email

    # Audit log before delete
    await log_event(
        db,
        "account_deleted",
        user_id=user_id,
        metadata={"email": user_email, "source": "clerk_webhook"},
    )

    # Suppression list
    email_hash = hashlib.sha256(user_email.lower().strip().encode()).hexdigest()
    db.add(
        SuppressionList(
            email_hash=email_hash,
            reason="account_deleted",
            requested_at=datetime.now(timezone.utc),
        )
    )

    # Archive credits
    await archive_credit_history(user_id, db)
    await db.flush()

    # Hard delete
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()
    logger.info("Deleted user %s from Clerk webhook", clerk_user_id)
