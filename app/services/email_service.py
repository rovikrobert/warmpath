"""Email service — verification and password reset emails.

Uses Resend SDK when RESEND_API_KEY is configured.
Falls back to console logging when no API key is set (local dev).
"""

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def generate_verification_token() -> str:
    """Generate a cryptographically random URL-safe token (32 bytes)."""
    return secrets.token_urlsafe(32)


def _send_email(to: str, subject: str, html: str) -> None:
    """Send an email via Resend SDK or log to console."""
    if settings.RESEND_API_KEY:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send(
            {
                "from": settings.FROM_EMAIL,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("Email sent to %s via Resend: %s", to, subject)
    else:
        logger.info("Email (console mode) to %s: %s\n%s", to, subject, html)


async def send_verification_email(user: User, db: AsyncSession) -> None:
    """Store verification token on user and send verification email."""
    token = generate_verification_token()
    user.email_verification_token = token
    user.email_verification_sent_at = datetime.now(timezone.utc)
    await db.flush()

    verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token}"
    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="color: #1e293b; margin-bottom: 8px;">
    <span style="color: #f59e0b;">~</span> WarmPath
  </h2>
  <p style="color: #475569; font-size: 16px; line-height: 1.5;">
    Welcome! Please verify your email address to unlock marketplace features.
  </p>
  <a href="{verify_url}"
     style="display: inline-block; background: #f59e0b; color: #fff; padding: 12px 28px;
            border-radius: 8px; text-decoration: none; font-weight: 600; margin: 20px 0;">
    Verify Email
  </a>
  <p style="color: #94a3b8; font-size: 13px;">
    Or copy this link: {verify_url}
  </p>
  <p style="color: #94a3b8; font-size: 13px;">
    This link expires in 24 hours.
  </p>
</div>"""

    _send_email(user.email, "Verify your WarmPath email", html)


async def send_password_reset_email(user: User, db: AsyncSession) -> None:
    """Generate a password reset token, store it, and send the reset email."""
    token = generate_verification_token()
    user.password_reset_token = token
    user.password_reset_sent_at = datetime.now(timezone.utc)
    await db.flush()

    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
    html = f"""\
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 40px 20px;">
  <h2 style="color: #1e293b; margin-bottom: 8px;">
    <span style="color: #f59e0b;">~</span> WarmPath
  </h2>
  <p style="color: #475569; font-size: 16px; line-height: 1.5;">
    We received a request to reset your password. Click the button below to set a new one.
  </p>
  <a href="{reset_url}"
     style="display: inline-block; background: #f59e0b; color: #fff; padding: 12px 28px;
            border-radius: 8px; text-decoration: none; font-weight: 600; margin: 20px 0;">
    Reset Password
  </a>
  <p style="color: #94a3b8; font-size: 13px;">
    Or copy this link: {reset_url}
  </p>
  <p style="color: #94a3b8; font-size: 13px;">
    This link expires in 1 hour. If you didn't request a password reset, ignore this email.
  </p>
</div>"""

    _send_email(user.email, "Reset your WarmPath password", html)


async def verify_token(token: str, db: AsyncSession) -> User:
    """Find user by verification token, validate expiry, mark as verified.

    Returns the verified User on success.
    Raises ValueError on invalid/expired token.
    """
    result = await db.execute(
        select(User).where(
            User.email_verification_token == token,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError("Invalid verification token")

    # Check token is less than 24 hours old
    if user.email_verification_sent_at is None:
        raise ValueError("Invalid verification token")

    now = datetime.now(timezone.utc)
    sent_at = user.email_verification_sent_at
    # Handle naive datetimes from SQLite (test env)
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    elapsed = (now - sent_at).total_seconds()
    if elapsed > 86400:  # 24 hours
        raise ValueError("Verification token has expired")

    # Mark verified and clear token fields
    user.email_verified = True
    user.email_verification_token = None
    user.email_verification_sent_at = None
    await db.flush()

    return user
