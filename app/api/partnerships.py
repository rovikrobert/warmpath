"""Partnership pipeline API — manage partnership opportunities and metrics."""

import math
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services import gtm_service
from app.utils.security import get_current_user

router = APIRouter()


def _require_admin(current_user: User) -> None:
    """Raise 403 if user is not an admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreatePartnershipRequest(BaseModel):
    partner_name: str = Field(..., max_length=200)
    partner_type: str = Field(..., max_length=30)
    partner_domain: str | None = Field(None, max_length=255)
    stage: str = Field("identified", max_length=30)
    contact_name: str | None = Field(None, max_length=200)
    contact_email: str | None = Field(None, max_length=255)
    estimated_users: int | None = None
    estimated_monthly_revenue: float | None = None
    notes: dict | None = None
    legal_review_status: str = Field("not_required", max_length=20)
    next_action: str | None = Field(None, max_length=500)
    next_action_date: date | None = None


class UpdatePartnershipRequest(BaseModel):
    partner_name: str | None = Field(None, max_length=200)
    partner_type: str | None = Field(None, max_length=30)
    partner_domain: str | None = Field(None, max_length=255)
    stage: str | None = Field(None, max_length=30)
    contact_name: str | None = Field(None, max_length=200)
    contact_email: str | None = Field(None, max_length=255)
    estimated_users: int | None = None
    estimated_monthly_revenue: float | None = None
    notes: dict | None = None
    legal_review_status: str | None = Field(None, max_length=20)
    next_action: str | None = Field(None, max_length=500)
    next_action_date: date | None = None


class AdvancePartnershipRequest(BaseModel):
    note: str | None = None


class LosePartnershipRequest(BaseModel):
    reason: str = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _partnership_to_dict(p) -> dict:
    return {
        "id": str(p.id),
        "partner_name": p.partner_name,
        "partner_domain": p.partner_domain,
        "partner_type": p.partner_type,
        "stage": p.stage,
        "stage_changed_at": p.stage_changed_at.isoformat()
        if p.stage_changed_at
        else None,
        "contact_name": p.contact_name,
        "contact_email": p.contact_email,
        "estimated_users": p.estimated_users,
        "estimated_monthly_revenue": (
            float(p.estimated_monthly_revenue)
            if p.estimated_monthly_revenue is not None
            else None
        ),
        "notes": p.notes,
        "legal_review_status": p.legal_review_status,
        "next_action": p.next_action,
        "next_action_date": p.next_action_date.isoformat()
        if p.next_action_date
        else None,
        "lost_reason": p.lost_reason,
        "created_by": str(p.created_by) if p.created_by else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _parse_uuid(raw: str) -> uuid.UUID:
    """Parse a string to UUID, raising 404 on invalid format."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Partnership not found",
        ) from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_partnerships(
    stage: str | None = Query(None),
    partner_type: str | None = Query(None),
    overdue: bool = Query(False),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List partnership opportunities with optional filters. Admin only."""
    _require_admin(current_user)
    partnerships = await gtm_service.list_partnerships(
        db, stage=stage, partner_type=partner_type, overdue=overdue
    )
    total = len(partnerships)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = partnerships[start:end]
    return {
        "data": [_partnership_to_dict(p) for p in page_items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/metrics")
async def get_pipeline_metrics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Partnership pipeline metrics and analytics. Admin only."""
    _require_admin(current_user)
    metrics = await gtm_service.get_pipeline_metrics(db)
    return {"data": metrics}


@router.get("/{partnership_id}")
async def get_partnership(
    partnership_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single partnership by ID. Admin only."""
    _require_admin(current_user)
    pid = _parse_uuid(partnership_id)
    partnership = await gtm_service.get_partnership(db, pid)
    if partnership is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Partnership not found",
        )
    return {"data": _partnership_to_dict(partnership)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_partnership(
    body: CreatePartnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new partnership opportunity. Admin only."""
    _require_admin(current_user)
    partnership = await gtm_service.create_partnership(
        db,
        partner_name=body.partner_name,
        partner_type=body.partner_type,
        partner_domain=body.partner_domain,
        stage=body.stage,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        estimated_users=body.estimated_users,
        estimated_monthly_revenue=body.estimated_monthly_revenue,
        notes=body.notes,
        legal_review_status=body.legal_review_status,
        next_action=body.next_action,
        next_action_date=body.next_action_date,
        created_by=current_user.id,
    )
    await db.commit()
    return {"data": _partnership_to_dict(partnership)}


@router.put("/{partnership_id}")
async def update_partnership(
    partnership_id: str,
    body: UpdatePartnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an existing partnership. Admin only."""
    _require_admin(current_user)
    pid = _parse_uuid(partnership_id)
    updates = body.model_dump(exclude_none=True)
    partnership = await gtm_service.update_partnership(db, pid, **updates)
    await db.commit()
    return {"data": _partnership_to_dict(partnership)}


@router.post("/{partnership_id}/advance")
async def advance_partnership(
    partnership_id: str,
    body: AdvancePartnershipRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Advance partnership to the next pipeline stage. Admin only."""
    _require_admin(current_user)
    pid = _parse_uuid(partnership_id)
    partnership = await gtm_service.advance_partnership(db, pid)
    await db.commit()
    return {"data": _partnership_to_dict(partnership)}


@router.post("/{partnership_id}/lose")
async def lose_partnership(
    partnership_id: str,
    body: LosePartnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a partnership as lost with a reason. Admin only."""
    _require_admin(current_user)
    pid = _parse_uuid(partnership_id)
    partnership = await gtm_service.lose_partnership(db, pid, lost_reason=body.reason)
    await db.commit()
    return {"data": _partnership_to_dict(partnership)}


@router.delete("/{partnership_id}")
async def delete_partnership(
    partnership_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a partnership. Admin only."""
    _require_admin(current_user)
    pid = _parse_uuid(partnership_id)
    partnership = await gtm_service.soft_delete_partnership(db, pid)
    await db.commit()
    return {"data": {"id": str(partnership.id), "deleted": True}}
