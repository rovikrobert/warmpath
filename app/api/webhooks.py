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

    return hmac.compa[RESEND_KEY_REDACTED](expected, signature)


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

    # TODO: Handle specific event types (checkout.session.completed, etc.)
    # For MVP, just acknowledge receipt.

    return {"data": {"received": True, "type": event_type}, "meta": {}}
