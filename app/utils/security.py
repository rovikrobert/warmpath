"""Clerk JWT verification and FastAPI auth dependencies.

Replaces the old custom JWT system (jose + passlib) with Clerk's
RS256 JWKS-based verification. Tokens are issued by Clerk's frontend
SDK and verified here against Clerk's public JWKS endpoint.
"""

import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer()


@lru_cache()
def _get_jwks_client():
    """Return a cached PyJWKClient for Clerk's JWKS endpoint."""
    from jwt import PyJWKClient

    jwks_url = f"https://{settings.CLERK_DOMAIN}/.well-known/jwks.json"
    jwks_client = PyJWKClient(jwks_url)
    return jwks_client


def verify_clerk_token(token: str) -> dict:
    """Verify a Clerk-issued JWT via JWKS (RS256).

    Returns the decoded payload dict on success.
    Raises HTTPException 401 on any verification failure.
    """
    import jwt as pyjwt

    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=f"https://{settings.CLERK_DOMAIN}",
        )
        return payload
    except pyjwt.PyJWTError as exc:
        logger.warning(
            "Clerk JWT verification failed: %s (domain=%s)", exc, settings.CLERK_DOMAIN
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        ) from None


async def _jit_provision_user(clerk_user_id: str, db: AsyncSession) -> User | None:
    """Create user on-the-fly from Clerk API when webhook hasn't arrived yet.

    Returns the created User, or None if Clerk API call fails.
    Handles race conditions (concurrent JIT + webhook) gracefully.
    """
    import hashlib

    import httpx
    from sqlalchemy.exc import IntegrityError

    if not settings.CLERK_SECRET_KEY:
        return None

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"https://api.clerk.com/v1/users/{clerk_user_id}",
                headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
                timeout=5.0,
            )
            if resp.status_code != 200:
                logger.warning(
                    "Clerk API returned %s for user %s", resp.status_code, clerk_user_id
                )
                return None
            data = resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Clerk API call failed for %s: %s", clerk_user_id, exc)
        return None

    # Extract email and name (same logic as clerk_webhooks._handle_user_created)
    email_addresses = data.get("email_addresses", [])
    email = ""
    email_verified = False
    if email_addresses:
        first = email_addresses[0]
        email = first.get("email_address", "")
        email_verified = first.get("verification", {}).get("status") == "verified"
    if not email:
        logger.warning("No email from Clerk API for %s", clerk_user_id)
        return None

    parts = [data.get("first_name", ""), data.get("last_name", "")]
    full_name = " ".join(p for p in parts if p).strip() or "User"

    # Check suppression list — don't re-provision deleted users.
    # When a user deletes their account, their email hash is added to the
    # suppression list.  If a stale Clerk session triggers JIT provisioning,
    # we must NOT silently recreate their account (which would dump them into
    # the onboarding wizard).  Returning None causes a 401 which the frontend
    # handles by clearing the Clerk session and showing the sign-up page.
    from app.models.privacy import SuppressionList

    email_hash = hashlib.sha256(email.lower().strip().encode()).hexdigest()
    suppression_check = await db.execute(
        select(SuppressionList).where(
            SuppressionList.email_hash == email_hash,
            SuppressionList.reason == "account_deleted",
        )
    )
    if suppression_check.scalars().first() is not None:
        logger.info(
            "Skipping JIT provision for deleted user (clerk_user_id=%s, email_hash=%s)",
            clerk_user_id,
            email_hash[:12],
        )
        return None

    user = User(
        email=email,
        full_name=full_name,
        clerk_user_id=clerk_user_id,
        email_verified=email_verified,
    )
    db.add(user)

    try:
        await db.flush()
    except IntegrityError:
        # Could be race condition (webhook arrived) or Clerk identity change
        # (e.g. user switched from email auth to Google OAuth — same email,
        # new clerk_user_id).
        await db.rollback()
        # First try by clerk_user_id (normal race condition)
        result = await db.execute(
            select(User).where(
                User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing
        # Then try by email — Clerk identity changed, update clerk_user_id
        if email:
            result = await db.execute(
                select(User).where(User.email == email, User.deleted_at.is_(None))
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.clerk_user_id = clerk_user_id
                await db.commit()
                logger.info(
                    "Updated clerk_user_id for %s (email=%s)", clerk_user_id, email
                )
                return existing
        return None

    # Award welcome bonus — the suppression check above already blocked
    # deleted users, so anyone reaching here is genuinely new.
    from app.services.credits import earn_credits

    suppression_result = await db.execute(
        select(SuppressionList).where(
            SuppressionList.email_hash == email_hash,
            SuppressionList.reason == "account_deleted",
        )
    )
    if suppression_result.scalars().first() is None:
        bonus = 500 if settings.BETA_SANDBOX_MODE else 50
        await earn_credits(user.id, bonus, "welcome_bonus", db, skip_daily_cap=True)

    await db.commit()
    logger.info("JIT-provisioned user %s (clerk_user_id=%s)", user.id, clerk_user_id)
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify Clerk JWT, look up user by clerk_user_id, return User."""
    payload = verify_clerk_token(credentials.credentials)
    clerk_user_id = payload.get("sub")
    if not clerk_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing subject",
        )
    result = await db.execute(
        select(User).where(
            User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        # JIT provisioning: webhook may not have arrived yet
        user = await _jit_provision_user(clerk_user_id, db)
    if user is None:
        logger.warning("No DB user for clerk_user_id=%s", clerk_user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found"
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated"
        )
    return user


async def require_verified_email(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency that requires the user's email to be verified.

    Use this on marketplace endpoints (search, intro requests, credit
    purchases). Own-network features (CSV upload, contacts, search) are
    allowed without verification.
    """
    if not current_user.email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email to access marketplace features",
        )
    return current_user
