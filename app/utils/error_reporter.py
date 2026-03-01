"""Error alerting via Telegram for beta user onboarding.

When unhandled 500 errors occur, sends a Telegram message to the founder
and saves a local copy. Rate-limited to avoid spam (max 1 alert per
endpoint per 5 minutes).
"""

import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

ALERT_DIR = Path("agents/chief_of_staff/reports/error_alerts")
_recent_alerts: dict[str, float] = {}
_COOLDOWN_SECONDS = 300  # 5 minutes per endpoint


def _should_alert(endpoint_key: str) -> bool:
    """Rate limit: max 1 alert per endpoint per 5 minutes."""
    now = time.monotonic()
    last = _recent_alerts.get(endpoint_key)
    if last and now - last < _COOLDOWN_SECONDS:
        return False
    _recent_alerts[endpoint_key] = now
    return True


def _write_to_finding_store(finding: dict) -> None:
    """Best-effort write to FindingStore for agent consumption."""
    try:
        import asyncio

        from app.agent_runtime.finding_store import FindingStore
        from app.config import settings

        if not settings.REDIS_URL:
            return

        store = FindingStore(redis_url=settings.REDIS_URL)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(store.classify_findings([finding]))
        finally:
            loop.close()
    except Exception:
        logger.warning("FindingStore write failed for error alert", exc_info=True)


def send_error_alert(
    method: str,
    path: str,
    error: Exception,
    user_email: str | None = None,
) -> str | None:
    """Generate an error alert for a 500 error.

    Sends via Telegram if configured, always saves a local copy.
    Returns the file path if saved, None if rate-limited or failed.
    """
    endpoint_key = f"{method}:{path}"
    if not _should_alert(endpoint_key):
        return None

    try:
        ALERT_DIR.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        time_str = now.strftime("%H:%M UTC")
        date_str = now.strftime("%Y-%m-%d")
        error_type = type(error).__name__
        error_msg = str(error)[:200]

        # Get the last frame of the traceback for context
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        last_frame = ""
        for line in reversed(tb):
            if "File " in line and "/app/" in line:
                last_frame = line.strip()[:150]
                break

        user_line = f"User: {user_email}" if user_email else "User: unauthenticated"

        message = "\n".join(
            [
                f"BUG ALERT [{time_str}]",
                "",
                f"{method} {path}",
                f"{error_type}: {error_msg}",
                user_line,
                "",
                last_frame if last_frame else "No app-level traceback",
                "",
                "Fix needed. Check logs for full trace.",
            ]
        )

        filename = f"error-alert-{date_str}-{now.strftime('%H%M%S')}.txt"
        filepath = ALERT_DIR / filename
        filepath.write_text(message, encoding="utf-8")
        logger.info("Error alert saved: %s", filepath)

        # Write to FindingStore for agent consumption
        _write_to_finding_store(
            {
                "source_team": "engineering",
                "category": "http_500_error",
                "title": f"500 error: {method} {path} — {error_type}",
                "severity": "high",
                "metadata": {
                    "method": method,
                    "path": path,
                    "error_type": error_type,
                    "error_message": error_msg,
                    "user_email": user_email or "unauthenticated",
                },
            }
        )

        # Send via Telegram if configured
        if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
            _send_via_telegram(message)

        return str(filepath)

    except Exception:
        logger.warning("Failed to generate error alert", exc_info=True)
        return None


def _send_via_telegram(message: str) -> None:
    """Send error alert via Telegram Bot API.

    Splits long messages into multiple parts if needed.
    """
    try:
        import httpx

        from agents.chief_of_staff.telegram_bridge import split_telegram_message

        token = os.environ["TELEGRAM_BOT_TOKEN"]
        chat_id = os.environ["TELEGRAM_CHAT_ID"]

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        chunks = split_telegram_message(message)
        with httpx.Client(timeout=10.0) as client:
            for chunk in chunks:
                payload = {"chat_id": chat_id, "text": chunk}
                response = client.post(url, json=payload)
                response.raise_for_status()
        logger.info(
            "Error alert sent via Telegram (%d part%s)",
            len(chunks),
            "s" if len(chunks) > 1 else "",
        )
    except Exception:
        logger.warning("Telegram error alert failed", exc_info=True)
