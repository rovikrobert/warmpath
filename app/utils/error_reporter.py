"""WhatsApp error alerting for beta user onboarding.

When unhandled 500 errors occur, generates a WhatsApp-formatted message
so the founder can be notified immediately. Phase 1 saves to file,
Phase 2 sends via Twilio.

The alerts include: endpoint, method, error type, error message,
and user context (if authenticated). Rate-limited to avoid spam
(max 1 alert per endpoint per 5 minutes).
"""

import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

WHATSAPP_DIR = Path("agents/chief_of_staff/reports/whatsapp")
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


def send_error_alert(
    method: str,
    path: str,
    error: Exception,
    user_email: str | None = None,
) -> str | None:
    """Generate a WhatsApp error alert for a 500 error.

    Returns the file path if saved, None if rate-limited or failed.
    """
    endpoint_key = f"{method}:{path}"
    if not _should_alert(endpoint_key):
        return None

    try:
        WHATSAPP_DIR.mkdir(parents=True, exist_ok=True)

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

        filename = f"whatsapp-error-{date_str}-{now.strftime('%H%M%S')}.txt"
        filepath = WHATSAPP_DIR / filename
        filepath.write_text(message, encoding="utf-8")
        logger.info("Error alert saved: %s", filepath)

        # Phase 2: Send via Twilio if configured
        if os.environ.get("TWILIO_ACCOUNT_SID"):
            _send_via_twilio(message)

        return str(filepath)

    except Exception:
        logger.warning("Failed to generate error alert", exc_info=True)
        return None


def _send_via_twilio(message: str) -> None:
    """Send error alert via Twilio WhatsApp (Phase 2)."""
    try:
        import httpx

        account_sid = os.environ["TWILIO_ACCOUNT_SID"]
        auth_token = os.environ["TWILIO_AUTH_TOKEN"]
        from_number = os.environ["TWILIO_WHATSAPP_FROM"]
        to_number = os.environ["ROVIK_WHATSAPP_NUMBER"]

        url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
        data = {
            "From": f"whatsapp:{from_number}",
            "To": f"whatsapp:{to_number}",
            "Body": message,
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, data=data, auth=(account_sid, auth_token))
            response.raise_for_status()
            logger.info("Error alert sent via Twilio: %s", response.json().get("sid"))
    except Exception:
        logger.warning("Twilio error alert failed", exc_info=True)
