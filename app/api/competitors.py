"""Competitor intelligence API — manage competitor profiles and feature matrix."""

import math
import uuid

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


class CreateCompetitorRequest(BaseModel):
    name: str = Field(..., max_length=200)
    category: str = Field(..., max_length=30)
    domain: str | None = Field(None, max_length=255)
    features: dict | None = None
    pricing: dict | None = None
    positioning: dict | None = None
    target_market: str | None = Field(None, max_length=200)
    funding_stage: str | None = Field(None, max_length=50)
    employee_count: int | None = None
    strengths: dict | None = None
    weaknesses: dict | None = None
    threat_level: str = Field("medium", max_length=20)
    source_urls: dict | None = None


class UpdateCompetitorRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    category: str | None = Field(None, max_length=30)
    domain: str | None = Field(None, max_length=255)
    features: dict | None = None
    pricing: dict | None = None
    positioning: dict | None = None
    target_market: str | None = Field(None, max_length=200)
    funding_stage: str | None = Field(None, max_length=50)
    employee_count: int | None = None
    strengths: dict | None = None
    weaknesses: dict | None = None
    threat_level: str | None = Field(None, max_length=20)
    source_urls: dict | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _competitor_to_dict(c) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "domain": c.domain,
        "category": c.category,
        "features": c.features,
        "pricing": c.pricing,
        "positioning": c.positioning,
        "target_market": c.target_market,
        "funding_stage": c.funding_stage,
        "employee_count": c.employee_count,
        "strengths": c.strengths,
        "weaknesses": c.weaknesses,
        "threat_level": c.threat_level,
        "last_scraped_at": c.last_scraped_at.isoformat() if c.last_scraped_at else None,
        "source_urls": c.source_urls,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _parse_uuid(raw: str) -> uuid.UUID:
    """Parse a string to UUID, raising 404 on invalid format."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competitor not found",
        ) from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_competitors(
    category: str | None = Query(None),
    threat_level: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all active competitors with optional filters. Admin only."""
    _require_admin(current_user)
    competitors = await gtm_service.list_competitors(
        db, category=category, threat_level=threat_level
    )
    total = len(competitors)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = competitors[start:end]
    return {
        "data": [_competitor_to_dict(c) for c in page_items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/matrix")
async def get_competitor_matrix(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Feature comparison matrix across all active competitors. Admin only."""
    _require_admin(current_user)
    matrix = await gtm_service.get_competitor_matrix(db)
    return {"data": matrix}


@router.get("/{competitor_id}")
async def get_competitor(
    competitor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single competitor by ID. Admin only."""
    _require_admin(current_user)
    cid = _parse_uuid(competitor_id)
    competitor = await gtm_service.get_competitor(db, cid)
    if competitor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Competitor not found",
        )
    return {"data": _competitor_to_dict(competitor)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_competitor(
    body: CreateCompetitorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new competitor profile. Admin only."""
    _require_admin(current_user)
    competitor = await gtm_service.create_competitor(
        db,
        name=body.name,
        category=body.category,
        domain=body.domain,
        features=body.features,
        pricing=body.pricing,
        positioning=body.positioning,
        target_market=body.target_market,
        funding_stage=body.funding_stage,
        employee_count=body.employee_count,
        strengths=body.strengths,
        weaknesses=body.weaknesses,
        threat_level=body.threat_level,
        source_urls=body.source_urls,
    )
    await db.commit()
    return {"data": _competitor_to_dict(competitor)}


@router.put("/{competitor_id}")
async def update_competitor(
    competitor_id: str,
    body: UpdateCompetitorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an existing competitor. Admin only."""
    _require_admin(current_user)
    cid = _parse_uuid(competitor_id)
    updates = body.model_dump(exclude_none=True)
    competitor = await gtm_service.update_competitor(db, cid, **updates)
    await db.commit()
    return {"data": _competitor_to_dict(competitor)}


@router.delete("/{competitor_id}")
async def delete_competitor(
    competitor_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a competitor. Admin only."""
    _require_admin(current_user)
    cid = _parse_uuid(competitor_id)
    competitor = await gtm_service.soft_delete_competitor(db, cid)
    await db.commit()
    return {"data": {"id": str(competitor.id), "deleted": True}}
