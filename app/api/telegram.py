"""Telegram webhook endpoint for CoS bidirectional communication.

Receives Telegram Bot updates, parses founder commands, and dispatches
them through the CoS pipeline.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from agents.shared.whatsapp_formatter import WhatsAppFormatter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, Any]:
    """Receive Telegram Bot webhook updates.

    Validates the secret token, extracts the message text,
    parses it using the shared reply grammar, and dispatches the command.
    """
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected_secret or x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    body = await request.json()
    message = body.get("message", {})
    text = message.get("text", "")

    if not text:
        return {"ok": True, "action": "ignored"}

    parsed = WhatsAppFormatter.parse_reply(text)
    command = parsed.get("command", "unknown")

    logger.info(
        "Telegram command received: %s (from chat %s)",
        command, message.get("chat", {}).get("id"),
    )

    return {"ok": True, "command": command, "parsed": parsed}
