"""Pydantic schemas for the referral system."""

from __futu[RESEND_KEY_REDACTED] import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ReferralCodeCreate(BaseModel):
    referral_type: str = Field(
        ..., pattern="^(nh_invite|js_invite)$", description="nh_invite or js_invite"
    )
    target_email: str | None = Field(
        None, max_length=255, description="Specific person to invite"
    )
    target_company_id: uuid.UUID | None = Field(
        None, description="Target company for NH invite"
    )
    max_uses: int | None = Field(
        None, ge=1, le=1000, description="Max redemptions (null=unlimited)"
    )


class ReferralCodeResponse(BaseModel):
    id: uuid.UUID
    code: str
    referral_type: str
    target_email: str | None = None
    target_company_id: uuid.UUID | None = None
    max_uses: int | None = None
    uses_count: int
    credits_per_conversion: int
    is_active: bool
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferralRedeemRequest(BaseModel):
    code: str = Field(..., max_length=32)


class ReferralConversionResponse(BaseModel):
    id: uuid.UUID
    referral_code_id: uuid.UUID
    referred_user_id: uuid.UUID
    conversion_event: str
    credits_awarded: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ReferralLeaderboardEntry(BaseModel):
    user_id: uuid.UUID
    full_name: str
    total_referrals: int
    total_conversions: int
    total_credits_earned: int
