"""Pricing benchmarks API — manage pricing intelligence and landscape summary."""

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


class CreateBenchmarkRequest(BaseModel):
    company_name: str = Field(..., max_length=200)
    product_category: str = Field(..., max_length=50)
    pricing_model: str = Field(..., max_length=30)
    domain: str | None = Field(None, max_length=255)
    tiers: dict | None = None
    free_tier_exists: bool | None = None
    lowest_paid_price: float | None = None
    enterprise_available: bool | None = None
    source_url: str | None = Field(None, max_length=500)
    notes: str | None = None


class UpdateBenchmarkRequest(BaseModel):
    company_name: str | None = Field(None, max_length=200)
    product_category: str | None = Field(None, max_length=50)
    pricing_model: str | None = Field(None, max_length=30)
    domain: str | None = Field(None, max_length=255)
    tiers: dict | None = None
    free_tier_exists: bool | None = None
    lowest_paid_price: float | None = None
    enterprise_available: bool | None = None
    source_url: str | None = Field(None, max_length=500)
    notes: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _benchmark_to_dict(b) -> dict:
    return {
        "id": str(b.id),
        "company_name": b.company_name,
        "domain": b.domain,
        "product_category": b.product_category,
        "pricing_model": b.pricing_model,
        "tiers": b.tiers,
        "free_tier_exists": b.free_tier_exists,
        "lowest_paid_price": float(b.lowest_paid_price)
        if b.lowest_paid_price is not None
        else None,
        "enterprise_available": b.enterprise_available,
        "source_url": b.source_url,
        "scraped_at": b.scraped_at.isoformat() if b.scraped_at else None,
        "notes": b.notes,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "updated_at": b.updated_at.isoformat() if b.updated_at else None,
    }


def _parse_uuid(raw: str) -> uuid.UUID:
    """Parse a string to UUID, raising 404 on invalid format."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark not found",
        ) from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_benchmarks(
    product_category: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all active pricing benchmarks with optional filters. Admin only."""
    _require_admin(current_user)
    benchmarks = await gtm_service.list_benchmarks(
        db, product_category=product_category
    )
    total = len(benchmarks)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = benchmarks[start:end]
    return {
        "data": [_benchmark_to_dict(b) for b in page_items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/summary")
async def get_pricing_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Pricing landscape summary and analytics. Admin only."""
    _require_admin(current_user)
    summary = await gtm_service.get_pricing_summary(db)
    return {"data": summary}


@router.get("/{benchmark_id}")
async def get_benchmark(
    benchmark_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single pricing benchmark by ID. Admin only."""
    _require_admin(current_user)
    bid = _parse_uuid(benchmark_id)
    benchmark = await gtm_service.get_benchmark(db, bid)
    if benchmark is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benchmark not found",
        )
    return {"data": _benchmark_to_dict(benchmark)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_benchmark(
    body: CreateBenchmarkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new pricing benchmark entry. Admin only."""
    _require_admin(current_user)
    benchmark = await gtm_service.create_benchmark(
        db,
        company_name=body.company_name,
        product_category=body.product_category,
        pricing_model=body.pricing_model,
        domain=body.domain,
        tiers=body.tiers,
        free_tier_exists=body.free_tier_exists,
        lowest_paid_price=body.lowest_paid_price,
        enterprise_available=body.enterprise_available,
        source_url=body.source_url,
        notes=body.notes,
    )
    await db.commit()
    return {"data": _benchmark_to_dict(benchmark)}


@router.put("/{benchmark_id}")
async def update_benchmark(
    benchmark_id: str,
    body: UpdateBenchmarkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an existing pricing benchmark. Admin only."""
    _require_admin(current_user)
    bid = _parse_uuid(benchmark_id)
    updates = body.model_dump(exclude_none=True)
    benchmark = await gtm_service.update_benchmark(db, bid, **updates)
    await db.commit()
    return {"data": _benchmark_to_dict(benchmark)}


@router.delete("/{benchmark_id}")
async def delete_benchmark(
    benchmark_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete a pricing benchmark. Admin only."""
    _require_admin(current_user)
    bid = _parse_uuid(benchmark_id)
    benchmark = await gtm_service.soft_delete_benchmark(db, bid)
    await db.commit()
    return {"data": {"id": str(benchmark.id), "deleted": True}}
