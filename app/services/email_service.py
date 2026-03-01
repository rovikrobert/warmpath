"""Email service — transactional email delivery.

Uses Resend SDK when RESEND_API_KEY is configured.
Falls back to console logging when no API key is set (local dev).

Rate-limited to stay within Resend's 2 req/sec cap.
"""

import logging
import threading
import time

from app.config import settings

logger = logging.getLogger(__name__)

# Resend allows 2 requests/sec. We enforce a minimum gap of 0.55s between
# sends to stay safely under the limit across all threads/workers.
_send_lock = threading.Lock()
_last_send_time: float = 0.0


def _send_email(
    to: str,
    subject: str,
    html: str,
    *,
    reply_to: str | None = None,
    from_email: str | None = None,
) -> str | None:
    """Send an email via Resend SDK or log to console.

    Returns the Resend message ID (for webhook matching) or None in console mode.
    Catches Resend API errors gracefully — logs the error and returns None
    so that the calling endpoint does not crash.

    Optional keyword args:
        reply_to: Sets the Reply-To header (e.g. network holder's email).
        from_email: Overrides the default FROM_EMAIL (e.g. "Name via WarmPath <intro@majiq.agency>").
    """
    if settings.RESEND_API_KEY:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        payload: dict = {
            "from": from_email or settings.FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "html": html,
        }
        if reply_to:
            payload["reply_to"] = reply_to

        # Throttle: enforce minimum gap between Resend API calls
        global _last_send_time  # noqa: PLW0603
        with _send_lock:
            elapsed = time.monotonic() - _last_send_time
            if elapsed < 0.55:
                time.sleep(0.55 - elapsed)
            _last_send_time = time.monotonic()

        try:
            result = resend.Emails.send(payload)
        except Exception:
            logger.exception("Resend API error sending to %s: %s", to, subject)
            return None
        email_id = (
            result.get("id")
            if isinstance(result, dict)
            else getattr(result, "id", None)
        )
        logger.info("Email sent to %s via Resend (id=%s): %s", to, email_id, subject)
        return email_id
    else:
        logger.info("Email (console mode) to %s: %s\n%s", to, subject, html)
        return None
