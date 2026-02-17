"""Stripe webhook endpoint — signature-verified payment events.

Verifies webhook signatures using HMAC-SHA256 against STRIPE_WEBHOOK_SECRET.
No stripe library needed — manual signature verification.
"""

import hashlib
import hmac
import logging
import time

from fastapi import APIRouter, HTTPException, Request, status

from app.config import settings

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
    import json

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
