"""Email verification service — token generation, "sending", and validation.

For MVP, send_verification_email just logs the verification URL to console.
Real email sending (SES/SendGrid/Postmark) is a post-deploy task.
"""

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)


def generate_verification_token() -> str:
    """Generate a cryptographically random URL-safe token (32 bytes)."""
    return secrets.token_urlsafe(32)


async def send_verification_email(user: User, db: AsyncSession) -> None:
    """Store verification token on user and "send" verification email.

    For MVP, this logs the URL to console. In production, this would
    dispatch an actual email via SES/SendGrid/Postmark.
    """
    token = generate_verification_token()
    user.email_verification_token = token
    user.email_verification_sent_at = datetime.now(timezone.utc)
    await db.flush()

    # MVP: log to console instead of sending email
    verify_url = f"https://warmpath.com/verify-email?token={token}"
    logger.info("Verification email for %s: %s", user.email, verify_url)


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
