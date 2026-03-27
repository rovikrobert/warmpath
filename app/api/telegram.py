"""Telegram webhook endpoint for CoS bidirectional communication.

Receives Telegram Bot updates, parses founder commands, executes
immediate commands (status, cost), and queues deferred ones.
Replies are sent back via the Telegram Bot API.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import os
import re
from collections import deque
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from agents.chief_of_staff.telegram_bridge import split_telegram_message
from agents.shared.message_formatter import MessageFormatter

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Team prefix parser
# ---------------------------------------------------------------------------

_VALID_TEAMS = {"engineering", "data", "product", "ops", "gtm", "finance", "cos"}


def _parse_team_prefix(text: str) -> tuple[str | None, str]:
    """Parse optional 'ask <team>:' prefix from message.

    Returns (team_or_None, remaining_query).
    """
    match = re.match(r"^ask\s+(\w+)\s*:\s*(.+)$", text, re.IGNORECASE)
    if match:
        team = match.group(1).lower()
        query = match.group(2).strip()
        if team in _VALID_TEAMS:
            return team, query
    return None, text


# ---------------------------------------------------------------------------
# Conversation buffer
# ---------------------------------------------------------------------------

_conversation_buffer: dict[int, deque[tuple[str, str]]] = {}
_MAX_HISTORY = 5


def _add_to_buffer(chat_id: int, user_msg: str, bot_response: str) -> None:
    """Store a user/bot exchange in the per-chat conversation buffer."""
    if chat_id not in _conversation_buffer:
        _conversation_buffer[chat_id] = deque(maxlen=_MAX_HISTORY)
    _conversation_buffer[chat_id].append((user_msg, bot_response))


def _get_history(chat_id: int) -> list[dict[str, str]]:
    """Return conversation history as a list of role/content dicts."""
    messages: list[dict[str, str]] = []
    for user_msg, bot_response in _conversation_buffer.get(chat_id, []):
        messages.append({"role": "user", "content": user_msg})
        messages.append({"role": "assistant", "content": bot_response})
    return messages


def _send_telegram_reply(chat_id: int, text: str) -> None:
    """Send a text reply to a Telegram chat (best-effort, sync).

    Splits long messages into multiple parts to stay within Telegram's
    4096-character limit.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.debug("TELEGRAM_BOT_TOKEN not set — skipping reply")
        return
    try:
        chunks = split_telegram_message(text)
        with httpx.Client(timeout=10.0) as client:
            for chunk in chunks:
                client.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk},
                )
    except Exception:
        logger.debug("Failed to send Telegram reply to %s", chat_id)


def _get_platform_stats() -> str:
    """Query live platform stats using the sync DB session."""
    from sqlalchemy import text as sa_text

    from app.database import _get_sync_engine

    engine = _get_sync_engine()
    batch_sql = sa_text(
        "SELECT"
        " (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL) AS total_users,"
        " (SELECT COUNT(DISTINCT user_id) FROM csv_uploads) AS users_with_uploads,"
        " (SELECT COUNT(*) FROM contacts WHERE deleted_at IS NULL) AS total_contacts,"
        " (SELECT COUNT(*) FROM marketplace_listings WHERE deleted_at IS NULL) AS marketplace_listings,"
        " (SELECT COUNT(*) FROM users WHERE plan_tier NOT IN ('free')"
        "   AND plan_tier IS NOT NULL AND deleted_at IS NULL) AS active_subscribers,"
        " (SELECT COUNT(*) FROM intro_facilitations) AS intro_requests,"
        " (SELECT COUNT(*) FROM users WHERE deleted_at IS NULL"
        "   AND created_at >= NOW() - INTERVAL '7 days') AS signups_7d"
    )
    with engine.connect() as conn:
        row = conn.execute(batch_sql).mappings().one()
        results: dict[str, int] = {k: (v or 0) for k, v in row.items()}

    pct_uploaded = (
        round(results["users_with_uploads"] / results["total_users"] * 100)
        if results["total_users"]
        else 0
    )

    return (
        "Platform Stats\n"
        "==============\n"
        f"Total users: {results['total_users']}\n"
        f"  Signups (7d): {results['signups_7d']}\n"
        f"  Uploaded CSV: {results['users_with_uploads']} ({pct_uploaded}%)\n"
        f"  Active subscribers: {results['active_subscribers']}\n"
        f"\n"
        f"Contacts: {results['total_contacts']}\n"
        f"Marketplace listings: {results['marketplace_listings']}\n"
        f"Intro requests: {results['intro_requests']}"
    )


def _handle_consultation(chat_id: int, raw_text: str) -> None:
    """Route a free-form message through the consultant engine."""
    from agents.shared.consultant import consult
    from agents.chief_of_staff.router import route_query

    # Parse optional "ask <team>:" prefix
    explicit_team, query = _parse_team_prefix(raw_text)

    # Determine target team
    if explicit_team:
        team = explicit_team
        routing_note = f"[{team}]"
    else:
        route = route_query(query)
        team = route.primary_team
        routing_note = f"[{team}] (auto-routed)"

    # Get conversation history
    history = _get_history(chat_id)

    # Run consultation
    response = consult(query, team=team, conversation_history=history)

    # Format reply — _send_telegram_reply handles splitting if too long
    reply = f"{routing_note}\n\n{response.answer}"
    _send_telegram_reply(chat_id, reply)

    # Update conversation buffer
    _add_to_buffer(chat_id, query, response.answer)


def _handle_command(
    command: str, parsed: dict, chat_id: int, is_founder: bool = False
) -> None:
    """Execute a command and reply via Telegram."""
    try:
        if command == "stats":
            if not is_founder:
                _send_telegram_reply(chat_id, "Stats is founder-only.")
                return
            result = _get_platform_stats()
            _send_telegram_reply(chat_id, result)

        elif command == "status":
            from agents.chief_of_staff.cos_agent import run_status

            result = run_status()
            _send_telegram_reply(chat_id, result)

        elif command == "approve":
            from agents.chief_of_staff.cos_learning import record_founder_decision

            item_id = parsed.get("item", "")
            record_founder_decision(item_id, "cos_recommendation", "approved")
            _send_telegram_reply(chat_id, f"Approved: {item_id}")

        elif command == "approve_item":
            if not is_founder:
                _send_telegram_reply(chat_id, "Execution is founder-only.")
                return
            item = parsed.get("item")
            value = parsed.get("value", "yes")
            reject = value in ("no", "n")
            _send_telegram_reply(
                chat_id,
                f"{'Rejecting' if reject else 'Executing'} decision #{item}...",
            )
            from app.tasks.approval_tasks import execute_telegram_approval

            execute_telegram_approval.delay(chat_id, item, reject)

        elif command == "choose":
            choice = parsed.get("choice", "")
            _send_telegram_reply(chat_id, f"Choice recorded: {choice}")

        elif command == "ship":
            feature = parsed.get("feature", "")
            _send_telegram_reply(
                chat_id,
                f"Ship request queued: {feature}\nWill execute on next daily cycle.",
            )

        elif command == "brief":
            topic = parsed.get(
                "topic", text if (text := parsed.get("raw", "")) else "general"
            )
            _send_telegram_reply(
                chat_id,
                f"Brief request queued: {topic}\nWill be included in next daily brief.",
            )

        else:
            # Free-form natural language → route to consultant engine
            raw_text = parsed.get("raw", "")
            if not raw_text:
                _send_telegram_reply(
                    chat_id,
                    "Commands: stats, status, cost, approve <id>, ship <feature>, brief me on <topic>\n"
                    "Or just type a question to consult any agent team.",
                )
                return

            if not is_founder:
                _send_telegram_reply(chat_id, "Free-form consultation is founder-only.")
                return

            _handle_consultation(chat_id, raw_text)
    except Exception as exc:
        logger.exception("Error handling Telegram command: %s", command)
        _send_telegram_reply(chat_id, f"Error processing '{command}': {str(exc)[:200]}")


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None),
) -> dict[str, Any]:
    """Receive Telegram Bot webhook updates.

    Validates the secret token, extracts the message text,
    parses it using the shared reply grammar, and dispatches the command.
    Replies are sent asynchronously in a background task.
    """
    expected_secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if not expected_secret or x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")

    body = await request.json()
    message = body.get("message", {})
    text = message.get("text", "")
    chat_id = message.get("chat", {}).get("id")

    if not text or not chat_id:
        return {"data": {"ok": True, "action": "ignored"}, "meta": {}}

    expected_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    is_founder = str(chat_id) == expected_chat_id

    parsed = MessageFormatter.parse_reply(text)
    command = parsed.get("command", "unknown")

    logger.info("Telegram command received: %s (from chat %s)", command, chat_id)

    background_tasks.add_task(_handle_command, command, parsed, chat_id, is_founder)

    return {"data": {"ok": True, "command": command}, "meta": {}}
