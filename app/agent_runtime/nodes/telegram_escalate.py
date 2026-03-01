from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)

# Rate limiting: max 5 escalations per 60 seconds
_MAX_PER_MINUTE = 5
_WINDOW_SECONDS = 60
_escalation_timestamps: deque[float] = deque()


def format_escalation_message(
    event_type: str, priority: str, findings_count: int, summary: str
) -> str:
    priority_icon = {
        "critical": "[!!!]",
        "high": "[!!]",
        "medium": "[!]",
        "low": "[.]",
    }.get(priority, "[?]")
    lines = [
        f"{priority_icon} Agent Runtime — {priority.upper()} {event_type}",
        "",
        summary,
        "",
        f"Findings: {findings_count}",
        "",
        "Reply 'approve' to let agents act, or 'reject' to stop.",
    ]
    return "\n".join(lines)


def _is_rate_limited() -> bool:
    """Check if we've exceeded the escalation rate limit."""
    now = time.monotonic()
    while _escalation_timestamps and now - _escalation_timestamps[0] > _WINDOW_SECONDS:
        _escalation_timestamps.popleft()
    return len(_escalation_timestamps) >= _MAX_PER_MINUTE


async def send_escalation(
    event_type: str, priority: str, findings_count: int, summary: str
) -> bool:
    """Send escalation to Telegram. Returns True if sent, False if rate-limited or failed."""
    import os

    if _is_rate_limited():
        logger.warning(
            "Escalation rate-limited (%d/%d in last %ds)",
            len(_escalation_timestamps),
            _MAX_PER_MINUTE,
            _WINDOW_SECONDS,
        )
        return False

    import httpx

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    msg = format_escalation_message(event_type, priority, findings_count, summary)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": msg},
            )
            resp.raise_for_status()
        _escalation_timestamps.append(time.monotonic())
        return True
    except Exception:
        logger.warning("Telegram escalation failed", exc_info=True)
        return False
