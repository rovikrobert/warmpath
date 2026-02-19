"""Email service — transactional email delivery.

Uses Resend SDK when RESEND_API_KEY is configured.
Falls back to console logging when no API key is set (local dev).
"""

import logging

from app.config import settings

logger = logging.getLogger(__name__)


def _send_email(to: str, subject: str, html: str) -> str | None:
    """Send an email via Resend SDK or log to console.

    Returns the Resend message ID (for webhook matching) or None in console mode.
    Catches Resend API errors gracefully — logs the error and returns None
    so that the calling endpoint does not crash.
    """
    if settings.RESEND_API_KEY:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        try:
            result = resend.Emails.send(
                {
                    "from": settings.FROM_EMAIL,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                }
            )
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
