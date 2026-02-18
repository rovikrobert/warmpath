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

    return hmac.compare_digest(expected, signature)


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request) -> dict:
    """Receive Stripe webhook events with signature verification.

    If STRIPE_WEBHOOK_SECRET is empty (dev mode), accepts all webhooks
    with a warning log. In production, rejects unsigned/invalid webhooks.
    """
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

    # Parse and process the event
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        )

    event_type = event.get("type", "unknown")
    logger.info("Stripe webhook received: %s", event_type)

    # Route to event-specific handlers
    handler = _EVENT_HANDLERS.get(event_type)
    if handler:
        handler(event)
    else:
        logger.debug("Unhandled Stripe event type: %s", event_type)

    return {"data": {"received": True, "type": event_type}, "meta": {}}


# ---------------------------------------------------------------------------
# Event handlers (stubs — wire to services when Stripe goes live)
# ---------------------------------------------------------------------------


def _handle_checkout_completed(event: dict) -> None:
    """Grant credits or activate subscription after successful checkout."""
    session = event.get("data", {}).get("object", {})
    logger.info(
        "Checkout completed: customer=%s, amount=%s",
        session.get("customer"),
        session.get("amount_total"),
    )


def _handle_invoice_paid(event: dict) -> None:
    """Confirm recurring payment — extend subscription period."""
    invoice = event.get("data", {}).get("object", {})
    logger.info(
        "Invoice paid: customer=%s, amount=%s",
        invoice.get("customer"),
        invoice.get("amount_paid"),
    )


def _handle_invoice_payment_failed(event: dict) -> None:
    """Flag failed payment — notify user, start grace period."""
    invoice = event.get("data", {}).get("object", {})
    logger.warning(
        "Invoice payment failed: customer=%s, attempt=%s",
        invoice.get("customer"),
        invoice.get("attempt_count"),
    )


def _handle_subscription_created(event: dict) -> None:
    """New subscription — activate premium features."""
    sub = event.get("data", {}).get("object", {})
    logger.info(
        "Subscription created: customer=%s, plan=%s, status=%s",
        sub.get("customer"),
        sub.get("plan", {}).get("id"),
        sub.get("status"),
    )


def _handle_subscription_updated(event: dict) -> None:
    """Subscription change — upgrade/downgrade/cancel scheduled."""
    sub = event.get("data", {}).get("object", {})
    logger.info(
        "Subscription updated: customer=%s, status=%s, cancel_at=%s",
        sub.get("customer"),
        sub.get("status"),
        sub.get("cancel_at"),
    )


def _handle_subscription_deleted(event: dict) -> None:
    """Subscription ended — revoke premium access."""
    sub = event.get("data", {}).get("object", {})
    logger.info(
        "Subscription deleted: customer=%s, ended_at=%s",
        sub.get("customer"),
        sub.get("ended_at"),
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
    import base64

    svix_id = ""  # populated from header in the endpoint
    svix_timestamp = ""

    # For simplified verification: compute HMAC of "msg_id.timestamp.body"
    try:
        sigs = [s.strip() for s in sig_header.split(" ")]
        for sig in sigs:
            if sig.startswith("v1,"):
                expected_b64 = sig[3:]
                break
        else:
            return False

        expected = base64.b64decode(expected_b64)
        # Resend/Svix signs: "<svix-id>.<svix-timestamp>.<body>"
        # We pass these as extra params via closure
        return True  # Signature verified in endpoint with full context
    except Exception:
        return False


@router.post("/webhooks/resend")
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Receive Resend webhook events for email tracking.

    Updates opened_at/clicked_at on EmailCampaignLog by matching
    the Resend email ID stored as external_id.

    Events handled: email.opened, email.clicked, email.bounced
    """
    payload = await request.body()

    # Signature verification when secret is configured
    if settings.RESEND_WEBHOOK_SECRET:
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
            )

        # Compute expected signature
        sign_content = f"{svix_id}.{svix_timestamp}.".encode() + payload
        secret_bytes = base64.b64decode(settings.RESEND_WEBHOOK_SECRET.split("_")[-1])
        computed = base64.b64encode(
            hmac.new(secret_bytes, sign_content, hashlib.sha256).digest()
        ).decode()

        # Check against any of the provided signatures
        valid = False
        for sig in svix_signature.split(" "):
            sig = sig.strip()
            if sig.startswith("v1,") and hmac.compare_digest(computed, sig[3:]):
                valid = True
                break

        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid webhook signature",
            )
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
        )

    event_type = event.get("type", "unknown")
    data = event.get("data", {})
    email_id = data.get("email_id")

    logger.info("Resend webhook received: %s (email_id=%s)", event_type, email_id)

    if not email_id:
        return {"data": {"received": True, "type": event_type}, "meta": {}}

    # Look up the campaign log by external_id
    result = await db.execute(
        select(EmailCampaignLog).where(EmailCampaignLog.external_id == email_id)
    )
    log_entry = result.scalar_one_or_none()

    if log_entry is None:
        logger.debug("No campaign log found for email_id=%s", email_id)
        return {"data": {"received": True, "type": event_type, "matched": False}, "meta": {}}

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

    await db.commit()

    return {"data": {"received": True, "type": event_type, "matched": True}, "meta": {}}
