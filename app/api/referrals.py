"""Referral system API endpoints.

POST /api/v1/referrals/create      — Generate a referral code
GET  /api/v1/referrals/mine        — List user's referral codes + stats
POST /api/v1/referrals/redeem      — Redeem a referral code during signup
GET  /api/v1/referrals/leaderboard — Top referrers
"""

from __futu[RESEND_KEY_REDACTED] import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.referral import (
    ReferralCodeCreate,
    ReferralCodeResponse,
    ReferralLeaderboardEntry,
    ReferralRedeemRequest,
)
from app.services import referral_service
from app.utils.security import get_current_user, requi[RESEND_KEY_REDACTED]

router = APIRouter()


@router.post("/create", status_code=status.HTTP_201_CREATED)
async def create_referral_code(
    body: ReferralCodeCreate,
    current_user: User = Depends(requi[RESEND_KEY_REDACTED]),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new referral code."""
    code = await referral_service.create_referral_code(
        owner_id=current_user.id,
        referral_type=body.referral_type,
        db=db,
        target_email=body.target_email,
        target_company_id=body.target_company_id,
        max_uses=body.max_uses,
    )
    await db.commit()
    return {
        "data": ReferralCodeResponse.model_validate(code).model_dump(mode="json"),
    }


@router.get("/mine")
async def list_my_referral_codes(
    current_user: User = Depends(requi[RESEND_KEY_REDACTED]),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all referral codes owned by the current user."""
    codes = await referral_service.get_user_referral_codes(
        user_id=current_user.id, db=db
    )
    return {
        "data": [
            ReferralCodeResponse.model_validate(c).model_dump(mode="json") for c in codes
        ],
        "meta": {"total": len(codes)},
    }


@router.post("/redeem")
async def redeem_referral_code(
    body: ReferralRedeemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Redeem a referral code (typically during or just after signup)."""
    try:
        ref_code = await referral_service.redeem_referral_code(
            code_str=body.code,
            referred_user_id=current_user.id,
            db=db,
        )
        await db.commit()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    # Funnel instrumentation: referral_redeem
    from app.models.enrichment import UsageLog

    db.add(
        UsageLog(
            user_id=current_user.id,
            action="referral_redeem",
            metadata_={"referral_type": ref_code.referral_type},
        )
    )
    await db.commit()

    return {
        "data": {
            "code": ref_code.code,
            "referral_type": ref_code.referral_type,
            "message": "Referral code redeemed successfully",
        },
    }


@router.get("/leaderboard")
async def referral_leaderboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the top referrers leaderboard."""
    entries = await referral_service.get_leaderboard(db=db, limit=10)
    return {
        "data": [
            ReferralLeaderboardEntry(**e).model_dump(mode="json") for e in entries
        ],
        "meta": {"total": len(entries)},
    }
