"""Referral system business logic.

Handles referral code creation, redemption, conversion tracking, and leaderboard.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.referral import ReferralCode, ReferralConversion
from app.models.user import User
from app.services.credits import earn_credits

# Credit amounts for referral conversions
CREDITS_NH_INVITE = 25  # JS earns when their invited NH uploads CSV
CREDITS_JS_INVITE = 50  # JS earns when their invited JS subscribes
REFERRAL_CODE_EXPIRY_DAYS = 90


def _generate_code() -> str:
    """Generate a unique 8-character referral code."""
    return secrets.token_urlsafe(6)[:8].upper()


async def create_referral_code(
    owner_id: uuid.UUID,
    referral_type: str,
    db: AsyncSession,
    target_email: str | None = None,
    target_company_id: uuid.UUID | None = None,
    max_uses: int | None = None,
) -> ReferralCode:
    """Create a new referral code for a user."""
    if referral_type not in ("nh_invite", "js_invite"):
        raise ValueError(f"Invalid referral_type: {referral_type}")

    credits_per = (
        CREDITS_NH_INVITE if referral_type == "nh_invite" else CREDITS_JS_INVITE
    )

    # For targeted invites, default to single-use
    if target_email and max_uses is None:
        max_uses = 1

    code = ReferralCode(
        owner_id=owner_id,
        code=_generate_code(),
        referral_type=referral_type,
        target_email=target_email,
        target_company_id=target_company_id,
        max_uses=max_uses,
        credits_per_conversion=credits_per,
        expires_at=datetime.now(timezone.utc)
        + timedelta(days=REFERRAL_CODE_EXPIRY_DAYS),
    )
    db.add(code)
    await db.flush()
    return code


async def get_user_referral_codes(
    user_id: uuid.UUID,
    db: AsyncSession,
) -> list[ReferralCode]:
    """Get all referral codes owned by a user."""
    result = await db.execute(
        select(ReferralCode)
        .where(ReferralCode.owner_id == user_id, ReferralCode.deleted_at.is_(None))
        .order_by(ReferralCode.created_at.desc())
    )
    return list(result.scalars().all())


async def redeem_referral_code(
    code_str: str,
    referred_user_id: uuid.UUID,
    db: AsyncSession,
) -> ReferralCode:
    """Redeem a referral code during signup.

    Returns the ReferralCode on success.
    Raises ValueError if code is invalid, expired, exhausted, or self-referral.
    """
    result = await db.execute(
        select(ReferralCode).where(
            ReferralCode.code == code_str,
            ReferralCode.is_active.is_(True),
            ReferralCode.deleted_at.is_(None),
        )
    )
    ref_code = result.scalar_one_or_none()

    if ref_code is None:
        raise ValueError("Invalid or inactive referral code")

    # Self-referral check
    if ref_code.owner_id == referred_user_id:
        raise ValueError("Cannot redeem your own referral code")

    # Expiry check — handle naive datetimes from SQLite
    now = datetime.now(timezone.utc)
    if ref_code.expires_at:
        exp = (
            ref_code.expires_at
            if ref_code.expires_at.tzinfo
            else ref_code.expires_at.replace(tzinfo=timezone.utc)
        )
        if exp < now:
            raise ValueError("Referral code has expired")

    # Usage limit check
    if ref_code.max_uses is not None and ref_code.uses_count >= ref_code.max_uses:
        raise ValueError("Referral code has reached its usage limit")

    # Check if this user already redeemed this code
    existing = await db.execute(
        select(ReferralConversion).where(
            ReferralConversion.referral_code_id == ref_code.id,
            ReferralConversion.referred_user_id == referred_user_id,
            ReferralConversion.conversion_event == "signup",
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("You have already redeemed this referral code")

    # Record the signup conversion
    conversion = ReferralConversion(
        referral_code_id=ref_code.id,
        referred_user_id=referred_user_id,
        conversion_event="signup",
        credits_awarded=0,  # Credits awarded on downstream events, not signup
    )
    db.add(conversion)

    # Increment uses
    ref_code.uses_count += 1
    await db.flush()

    return ref_code


async def record_conversion(
    referred_user_id: uuid.UUID,
    event: str,
    db: AsyncSession,
) -> ReferralConversion | None:
    """Record a conversion event and award credits to the referrer.

    Called when a referred user completes a key action (csv_upload, first_search,
    subscription). Returns the conversion record, or None if no referral applies.
    """
    if event not in ("csv_upload", "first_search", "subscription"):
        return None

    # Find the signup conversion for this user
    result = await db.execute(
        select(ReferralConversion)
        .where(
            ReferralConversion.referred_user_id == referred_user_id,
            ReferralConversion.conversion_event == "signup",
        )
        .limit(1)
    )
    signup_conversion = result.scalar_one_or_none()
    if not signup_conversion:
        return None  # User wasn't referred

    # Check if this event was already recorded
    existing = await db.execute(
        select(ReferralConversion).where(
            ReferralConversion.referral_code_id == signup_conversion.referral_code_id,
            ReferralConversion.referred_user_id == referred_user_id,
            ReferralConversion.conversion_event == event,
        )
    )
    if existing.scalar_one_or_none():
        return None  # Already recorded

    # Get the referral code to determine credits
    ref_code_result = await db.execute(
        select(ReferralCode).where(
            ReferralCode.id == signup_conversion.referral_code_id
        )
    )
    ref_code = ref_code_result.scalar_one_or_none()
    if not ref_code:
        return None

    credits = ref_code.credits_per_conversion

    # Record the conversion
    conversion = ReferralConversion(
        referral_code_id=ref_code.id,
        referred_user_id=referred_user_id,
        conversion_event=event,
        credits_awarded=credits,
    )
    db.add(conversion)

    # Award credits to the referrer
    await earn_credits(
        user_id=ref_code.owner_id,
        amount=credits,
        reason=f"referral_{event}",
        db=db,
        reference_id=conversion.id,
    )

    await db.flush()
    return conversion


async def get_leaderboard(
    db: AsyncSession,
    limit: int = 10,
) -> list[dict]:
    """Get the top referrers by total conversions."""
    result = await db.execute(
        select(
            ReferralCode.owner_id,
            User.full_name,
            func.count(ReferralConversion.id).label("total_conversions"),
            func.sum(ReferralConversion.credits_awarded).label("total_credits"),
        )
        .join(
            ReferralConversion, ReferralConversion.referral_code_id == ReferralCode.id
        )
        .join(User, User.id == ReferralCode.owner_id)
        .where(ReferralCode.deleted_at.is_(None))
        .group_by(ReferralCode.owner_id, User.full_name)
        .order_by(func.count(ReferralConversion.id).desc())
        .limit(limit)
    )
    rows = result.all()

    # Also get total referral codes per user
    code_counts = {}
    for row in rows:
        code_result = await db.execute(
            select(func.count(ReferralCode.id)).where(
                ReferralCode.owner_id == row.owner_id,
                ReferralCode.deleted_at.is_(None),
            )
        )
        code_counts[row.owner_id] = code_result.scalar() or 0

    return [
        {
            "user_id": row.owner_id,
            "full_name": row.full_name,
            "total_referrals": code_counts.get(row.owner_id, 0),
            "total_conversions": row.total_conversions,
            "total_credits_earned": row.total_credits or 0,
        }
        for row in rows
    ]
