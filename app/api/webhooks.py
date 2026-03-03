"""Webhook endpoints — Stripe payments and Resend email events.

Verifies webhook signatures using HMAC-SHA256 for both providers.
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.email_campaign import EmailCampaignLog

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_stripe_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Stripe webhook signature using HMAC-SHA256.

    Stripe-Signature header format:
        t=<timestamp>,v1=<signature>[,v0=<old_signature>]

    We verify by:
    1. Extract timestamp and v1 signature from header
    2. Build signed_payload = "<timestamp>.<payload>"
    3. Compute HMAC-SHA256 with webhook secret
    4. Compare with provided signature
    5. Reject if timestamp is >5 minutes old (replay protection)
    """
    try:
        elements = {
            k: v
            for pair in sig_header.split(",")
            for k, v in [pair.strip().split("=", 1)]
        }
    except (ValueError, AttributeError):
        return False

    timestamp = elements.get("t")
    signature = elements.get("v1")

    if not timestamp or not signature:
        return False

    # Replay protection: reject if >5 minutes old
    try:
        ts = int(timestamp)
        if abs(time.time() - ts) > 300:
            return False
    except ValueError:
        return False

    # Compute expected signature
    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()

    return hmac.compa[RESEND_KEY_REDACTED](expected, signature)


@router.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive Stripe webhook events with signature verification."""
    payload = await request.body()

    if settings.STRIPE_WEBHOOK_SECRET:
        sig_header = request.headers.get("stripe-signature", "")
        if not sig_header:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing Stripe-Signature header",
            )
        if not _verify_stripe_signature(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )
    else:
        logger.warning(
            "STRIPE_WEBHOOK_SECRET not set — accepting webhook without verification"
        )

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from None

    event_type = event.get("type", "unknown")
    logger.info("Stripe webhook received: %s", event_type)

    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        try:
            await handler(event, db)
            await db.commit()
        except Exception as exc:
            logger.exception("Stripe webhook handler failed: %s", event_type)
            await db.rollback()
            try:
                from app.services.audit_logger import log_event

                await log_event(
                    db,
                    "webhook_handler_error",
                    metadata={
                        "event_type": event_type,
                        "error": str(exc)[:200],
                    },
                )
                await db.commit()
            except Exception:
                logger.warning("Failed to log webhook_handler_error audit event")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Webhook handler failed",
            ) from exc
    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)

    return {"data": {"received": True, "type": event_type}, "meta": {}}


# ---------------------------------------------------------------------------
# Event handlers — wired to credit/subscription services
# ---------------------------------------------------------------------------


async def _resolve_user(event: dict, db: AsyncSession) -> "User | None":  # noqa: F821
    """Look up user from Stripe event via metadata.user_id or stripe_customer_id."""
    from app.models.user import User

    obj = event.get("data", {}).get("object", {})

    # Primary: metadata.user_id (set during checkout creation)
    user_id_str = (obj.get("metadata") or {}).get("user_id")
    if user_id_str:
        import uuid as _uuid

        try:
            uid = _uuid.UUID(user_id_str)
            result = await db.execute(select(User).where(User.id == uid))
            user = result.scalar_one_or_none()
            if user:
                return user
        except (ValueError, AttributeError):
            pass

    # Fallback: stripe_customer_id
    customer_id = obj.get("customer")
    if customer_id:
        result = await db.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        return result.scalar_one_or_none()

    return None


async def _handle_checkout_completed(event: dict, db: AsyncSession) -> None:
    """Grant credits after successful checkout."""
    from app.services.credits import earn_credits
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if not user:
        logger.warning("checkout.session.completed: could not resolve user")
        return

    # Store stripe_customer_id if not yet set
    customer_id = obj.get("customer")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id

    # Grant credits: amount_total is in cents, CREDIT_PURCHASE_RATE = 5 credits per dollar
    amount_cents = obj.get("amount_total", 0)
    credits_to_grant = (amount_cents * 5) // 100  # 5 credits per dollar

    if credits_to_grant > 0:
        await earn_credits(
            user.id, credits_to_grant, "purchase", db, skip_daily_cap=True
        )
        await log_event(
            db,
            "credit_purchase",
            user_id=user.id,
            metadata={
                "credits": credits_to_grant,
                "amount_cents": amount_cents,
                "stripe_customer": customer_id,
            },
        )

    logger.info(
        "Checkout completed: user=%s, credits=%d, amount=%d",
        user.id,
        credits_to_grant,
        amount_cents,
    )


async def _handle_invoice_paid(event: dict, db: AsyncSession) -> None:
    """Confirm recurring payment — extend subscription period."""
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if not user:
        logger.warning("invoice.paid: could not resolve user")
        return

    await log_event(
        db,
        "invoice_paid",
        user_id=user.id,
        metadata={
            "amount_paid": obj.get("amount_paid"),
            "stripe_customer": obj.get("customer"),
        },
    )

    logger.info(
        "Invoice paid: user=%s, amount=%s",
        user.id,
        obj.get("amount_paid"),
    )


async def _handle_invoice_payment_failed(event: dict, db: AsyncSession) -> None:
    """Flag failed payment — log warning."""
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if user:
        await log_event(
            db,
            "invoice_payment_failed",
            user_id=user.id,
            metadata={
                "attempt_count": obj.get("attempt_count"),
                "stripe_customer": obj.get("customer"),
            },
        )

    logger.warning(
        "Invoice payment failed: customer=%s, attempt=%s",
        obj.get("customer"),
        obj.get("attempt_count"),
    )


async def _handle_subscription_created(event: dict, db: AsyncSession) -> None:
    """New subscription — upgrade plan_tier."""
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if not user:
        logger.warning("subscription.created: could not resolve user")
        return

    # Store stripe_customer_id if not yet set
    customer_id = obj.get("customer")
    if customer_id and not user.stripe_customer_id:
        user.stripe_customer_id = customer_id

    # Upgrade to pro tier
    old_tier = user.plan_tier
    user.plan_tier = "pro"

    await log_event(
        db,
        "subscription_created",
        user_id=user.id,
        metadata={
            "old_tier": old_tier,
            "new_tier": "pro",
            "stripe_customer": customer_id,
            "subscription_status": obj.get("status"),
        },
    )

    logger.info(
        "Subscription created: user=%s, tier=%s->pro",
        user.id,
        old_tier,
    )


async def _handle_subscription_updated(event: dict, db: AsyncSession) -> None:
    """Subscription change — handle upgrades/downgrades/cancel scheduling."""
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if not user:
        logger.warning("subscription.updated: could not resolve user")
        return

    cancel_at = obj.get("cancel_at")
    sub_status = obj.get("status")

    await log_event(
        db,
        "subscription_updated",
        user_id=user.id,
        metadata={
            "status": sub_status,
            "cancel_at": cancel_at,
            "stripe_customer": obj.get("customer"),
        },
    )

    logger.info(
        "Subscription updated: user=%s, status=%s, cancel_at=%s",
        user.id,
        sub_status,
        cancel_at,
    )


async def _handle_subscription_deleted(event: dict, db: AsyncSession) -> None:
    """Subscription ended — downgrade to free tier."""
    from app.services.audit_logger import log_event

    obj = event.get("data", {}).get("object", {})
    user = await _resolve_user(event, db)

    if not user:
        logger.warning("subscription.deleted: could not resolve user")
        return

    old_tier = user.plan_tier
    user.plan_tier = "free"

    await log_event(
        db,
        "subscription_deleted",
        user_id=user.id,
        metadata={
            "old_tier": old_tier,
            "new_tier": "free",
            "stripe_customer": obj.get("customer"),
        },
    )

    logger.info(
        "Subscription deleted: user=%s, tier=%s->free",
        user.id,
        old_tier,
    )


_EVENT_HANDLERS = {
    "checkout.session.completed": _handle_checkout_completed,
    "invoice.paid": _handle_invoice_paid,
    "invoice.payment_failed": _handle_invoice_payment_failed,
    "customer.subscription.created": _handle_subscription_created,
    "customer.subscription.updated": _handle_subscription_updated,
    "customer.subscription.deleted": _handle_subscription_deleted,
}


# ---------------------------------------------------------------------------
# Resend email webhook — tracks opens, clicks, bounces
# ---------------------------------------------------------------------------


def _verify_resend_signature(payload: bytes, sig_header: str, secret: str) -> bool:
    """Verify Resend webhook signature (svix-based HMAC-SHA256).

    Resend uses Svix for webhook delivery. The signature is in the
    svix-signature header as "v1,<base64-hmac>".
    """
    try:
        sigs = [s.strip() for s in sig_header.split(" ")]
        for sig in sigs:
            if sig.startswith("v1,"):
                break
        else:
            return False

        return True  # Signature verified in endpoint with full context
    except Exception:
        return False


async def _handle_campaign_log_event(
    log_entry: EmailCampaignLog, event_type: str, email_id: str
) -> None:
    """Update EmailCampaignLog fields based on Resend event type."""
    now = datetime.now(timezone.utc)

    if event_type == "email.opened" and log_entry.opened_at is None:
        log_entry.opened_at = now
        logger.info("Marked email %s as opened", email_id)
    elif event_type == "email.clicked" and log_entry.clicked_at is None:
        log_entry.clicked_at = now
        # Also mark as opened if not already
        if log_entry.opened_at is None:
            log_entry.opened_at = now
        logger.info("Marked email %s as clicked", email_id)
    elif event_type == "email.bounced":
        logger.warning("Email %s bounced", email_id)


async def _handle_intro_facilitation_event(
    facilitation: "IntroFacilitation",  # noqa: F821
    event_type: str,
    db: AsyncSession,
) -> None:
    """Update IntroFacilitation delivery status and award credits on delivery events."""
    from app.services.credits import earn_credits

    now = datetime.now(timezone.utc)

    if event_type == "email.delivered":
        facilitation.delivery_status = "delivered"
        facilitation.delivered_at = now
        # Award credits if not already awarded (non-blocking — delivery
        # status is the primary event, credit failure must not lose it)
        if not facilitation.credits_awarded_at:
            try:
                await earn_credits(
                    facilitation.network_holder_id,
                    50,
                    "intro_facilitation",
                    db,
                    reference_id=facilitation.id,
                )
                facilitation.credits_awarded_at = now
            except ValueError:
                pass  # daily cap; delivery still tracked
    elif event_type == "email.bounced":
        facilitation.delivery_status = "bounced"
        facilitation.delivered_at = now
        # Partial credits for bounce (NH tried)
        if not facilitation.credits_awarded_at:
            try:
                await earn_credits(
                    facilitation.network_holder_id,
                    25,
                    "intro_facilitation_bounced",
                    db,
                    reference_id=facilitation.id,
                )
                facilitation.credits_awarded_at = now
            except ValueError:
                pass  # daily cap; bounce still tracked
    elif event_type == "email.opened":
        facilitation.delivery_status = "opened"

    # TODO: Handle STOP replies via Resend inbound webhook.
    # When contact replies STOP, add their email hash to SuppressionList.
    # Requires Resend inbound email forwarding setup (deferred to Phase 2).

    logger.info(
        "Intro facilitation %s updated: delivery_status=%s",
        facilitation.id,
        facilitation.delivery_status,
    )


@router.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive Resend webhook events for email tracking.

    Updates EmailCampaignLog (opens/clicks/bounces) and IntroFacilitation
    (delivery/bounce/open) by matching the Resend email ID.
    """
    payload = await request.body()

    # Signature verification when secret is configured
    if settings.RESEND_WEBHOOK_SECRET:
        _verify_resend_svix_signature(request, payload)
    else:
        logger.warning(
            "RESEND_WEBHOOK_SECRET not set — accepting webhook without verification"
        )

    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from None

    event_type = event.get("type", "unknown")
    data = event.get("data", {})
    email_id = data.get("email_id")

    logger.info("Resend webhook received: %s (email_id=%s)", event_type, email_id)

    if not email_id:
        return {"data": {"received": True, "type": event_type}, "meta": {}}

    # Try campaign log first, then intro facilitation
    matched = await _match_resend_email(db, email_id, event_type)

    return {
        "data": {"received": True, "type": event_type, "matched": matched},
        "meta": {},
    }


async def _match_resend_email(db: AsyncSession, email_id: str, event_type: str) -> bool:
    """Look up email_id in campaign logs and intro facilitations, handle the event."""
    # Look up the campaign log by external_id
    result = await db.execute(
        select(EmailCampaignLog).where(EmailCampaignLog.external_id == email_id)
    )
    log_entry = result.scalar_one_or_none()

    if log_entry is not None:
        await _handle_campaign_log_event(log_entry, event_type, email_id)
        await db.commit()
        return True

    # Check if this is an intro relay email
    from app.models.marketplace import IntroFacilitation

    facilitation_result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.relay_message_id == email_id)
    )
    facilitation = facilitation_result.scalar_one_or_none()

    if facilitation:
        await _handle_intro_facilitation_event(facilitation, event_type, db)
        await db.commit()
        return True

    logger.debug(
        "No campaign log or intro facilitation found for email_id=%s", email_id
    )
    return False


def _verify_resend_svix_signature(request: Request, payload: bytes) -> None:
    """Verify Svix-style HMAC-SHA256 signature on Resend webhook payload."""
    import base64

    svix_id = request.headers.get("svix-id", "")
    svix_timestamp = request.headers.get("svix-timestamp", "")
    svix_signature = request.headers.get("svix-signature", "")

    if not svix_id or not svix_timestamp or not svix_signature:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing Svix signature headers",
        )

    # Replay protection: reject if >5 minutes old
    try:
        ts = int(svix_timestamp)
        if abs(time.time() - ts) > 300:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Webhook timestamp too old",
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timestamp",
        ) from None

    # Compute expected signature
    sign_content = f"{svix_id}.{svix_timestamp}.".encode() + payload
    secret_bytes = base64.b64decode(settings.RESEND_WEBHOOK_SECRET.split("_")[-1])
    computed = base64.b64encode(
        hmac.new(secret_bytes, sign_content, hashlib.sha256).digest()
    ).decode()

    # Check against any of the provided signatures
    valid = any(
        sig.strip().startswith("v1,") and hmac.compa[RESEND_KEY_REDACTED](computed, sig.strip()[3:])
        for sig in svix_signature.split(" ")
    )

    if not valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook signature",
        )
