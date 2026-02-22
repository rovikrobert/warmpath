"""Public intro review endpoint — token-based access to intro summary.

No authentication required. Rate-limited via audit_logs counting.
"""

import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit import AuditLog
from app.models.marketplace import IntroFacilitation, MarketplaceListing
from app.models.user import User
from app.services.audit_logger import log_event
from app.utils.security import get_current_user

router = APIRouter()

RATE_LIMIT_ACTION = "intro_review_access"
RATE_LIMIT_MAX = 20  # requests per IP per minute


def _client_ip(request: Request) -> str:
    """Extract client IP, preferring X-Forwarded-For for proxied deployments."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _first_name(full_name: str) -> str:
    """Extract first name from full name."""
    parts = (full_name or "").split()
    return parts[0] if parts else ""


async def _check_rate_limit(ip: str, db: AsyncSession) -> None:
    """Raise 429 if IP exceeded rate limit in last minute."""
    one_minute_ago = datetime.now(timezone.utc) - timedelta(minutes=1)
    result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == RATE_LIMIT_ACTION,
            AuditLog.ip_address == ip,
            AuditLog.created_at >= one_minute_ago,
        )
    )
    count = result.scalar() or 0
    if count >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )


@router.get("/intro-review/{token}")
async def get_intro_review(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: view intro summary by review token.

    No authentication required. Returns limited, non-PII data.
    Rate-limited to 20 requests per IP per minute.
    """
    ip = _client_ip(request)
    ua = request.headers.get("user-agent", "")

    # Rate limit check
    await _check_rate_limit(ip, db)

    # Look up facilitation by token
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(IntroFacilitation)
        .options(
            selectinload(IntroFacilitation.job_seeker),
            selectinload(IntroFacilitation.network_holder),
            selectinload(IntroFacilitation.marketplace_listing).selectinload(
                MarketplaceListing.company
            ),
        )
        .where(
            IntroFacilitation.review_token == token,
            IntroFacilitation.review_token_expires_at > now,
        )
    )
    facilitation = result.scalar_one_or_none()

    # Audit log every access (token hash, not raw token)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    await log_event(
        db,
        RATE_LIMIT_ACTION,
        ip_address=ip,
        user_agent=ua,
        metadata={"token_hash": token_hash, "found": facilitation is not None},
    )

    if facilitation is None:
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This introduction has expired or is no longer available.",
        )

    # Extract non-PII data
    js_user = facilitation.job_seeker
    nh_user = facilitation.network_holder
    listing = facilitation.marketplace_listing
    snapshot = facilitation.job_seeker_profile_snapshot or {}

    js_first = _first_name(js_user.full_name) if js_user else ""
    js_headline = snapshot.get("headline", "")
    nh_first = _first_name(nh_user.full_name) if nh_user else ""
    target_company = listing.company.name if listing and listing.company else ""
    sent_at = facilitation.delivered_at or facilitation.reviewed_at

    await db.commit()

    return {
        "data": {
            "job_seeker_first_name": js_first,
            "job_seeker_headline": js_headline,
            "introducer_first_name": nh_first,
            "target_company": target_company,
            "status": facilitation.status,
            "sent_at": sent_at.isoformat() if sent_at else None,
        },
        "meta": {},
    }


@router.delete("/intro-review/{token}")
async def revoke_intro_review_token(
    token: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Revoke a review token. Only the job seeker or network holder can do this."""
    result = await db.execute(
        select(IntroFacilitation).where(IntroFacilitation.review_token == token)
    )
    facilitation = result.scalar_one_or_none()

    if facilitation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token not found.",
        )

    # Only the JS or NH on this facilitation can revoke
    if current_user.id not in (
        facilitation.job_seeker_id,
        facilitation.network_holder_id,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to revoke this token.",
        )

    facilitation.review_token = None
    facilitation.review_token_expires_at = None

    await log_event(
        db,
        "intro_review_token_revoked",
        user_id=current_user.id,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        metadata={
            "facilitation_id": str(facilitation.id),
            "token_hash": hashlib.sha256(token.encode()).hexdigest(),
        },
    )

    await db.commit()
    return {"data": {"revoked": True}, "meta": {}}
