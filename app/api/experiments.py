"""GTM experiments API — manage A/B tests and growth experiments."""

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


def _requi[RESEND_KEY_REDACTED](current_user: User) -> None:
    """Raise 403 if user is not an admin."""
    if not getattr(current_user, "is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class CreateExperimentRequest(BaseModel):
    name: str = Field(..., max_length=200)
    experiment_type: str = Field(..., max_length=30)
    hypothesis: str | None = None
    status: str = Field("draft", max_length=20)
    variants: dict | None = None
    metrics: dict | None = None
    target_sample_size: int | None = None


class UpdateExperimentRequest(BaseModel):
    name: str | None = Field(None, max_length=200)
    experiment_type: str | None = Field(None, max_length=30)
    hypothesis: str | None = None
    variants: dict | None = None
    metrics: dict | None = None
    target_sample_size: int | None = None


class CompleteExperimentRequest(BaseModel):
    results: dict | None = None
    conclusion: str | None = None
    recommendation: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _experiment_to_dict(e) -> dict:
    return {
        "id": str(e.id),
        "name": e.name,
        "hypothesis": e.hypothesis,
        "experiment_type": e.experiment_type,
        "status": e.status,
        "started_at": e.started_at.isoformat() if e.started_at else None,
        "ended_at": e.ended_at.isoformat() if e.ended_at else None,
        "variants": e.variants,
        "metrics": e.metrics,
        "target_sample_size": e.target_sample_size,
        "results": e.results,
        "conclusion": e.conclusion,
        "recommendation": e.recommendation,
        "created_by": str(e.created_by) if e.created_by else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def _parse_uuid(raw: str) -> uuid.UUID:
    """Parse a string to UUID, raising 404 on invalid format."""
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment not found",
        ) from e


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("")
async def list_experiments(
    status: str | None = Query(None),
    experiment_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all active experiments with optional filters. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    experiments = await gtm_service.list_experiments(
        db, status=status, experiment_type=experiment_type
    )
    total = len(experiments)
    total_pages = max(1, math.ceil(total / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_items = experiments[start:end]
    return {
        "data": [_experiment_to_dict(e) for e in page_items],
        "meta": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    }


@router.get("/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single experiment by ID. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    eid = _parse_uuid(experiment_id)
    experiment = await gtm_service.get_experiment(db, eid)
    if experiment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Experiment not found",
        )
    return {"data": _experiment_to_dict(experiment)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_experiment(
    body: CreateExperimentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new GTM experiment. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    experiment = await gtm_service.create_experiment(
        db,
        name=body.name,
        experiment_type=body.experiment_type,
        hypothesis=body.hypothesis,
        status=body.status,
        variants=body.variants,
        metrics=body.metrics,
        target_sample_size=body.target_sample_size,
        created_by=current_user.id,
    )
    await db.commit()
    return {"data": _experiment_to_dict(experiment)}


@router.put("/{experiment_id}")
async def update_experiment(
    experiment_id: str,
    body: UpdateExperimentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an existing experiment. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    eid = _parse_uuid(experiment_id)
    updates = body.model_dump(exclude_none=True)
    experiment = await gtm_service.update_experiment(db, eid, **updates)
    await db.commit()
    return {"data": _experiment_to_dict(experiment)}


@router.post("/{experiment_id}/start")
async def start_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Start a draft experiment (transition to running). Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    eid = _parse_uuid(experiment_id)
    experiment = await gtm_service.start_experiment(db, eid)
    await db.commit()
    return {"data": _experiment_to_dict(experiment)}


@router.post("/{experiment_id}/complete")
async def complete_experiment(
    experiment_id: str,
    body: CompleteExperimentRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Complete a running/paused experiment with results. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    eid = _parse_uuid(experiment_id)
    kwargs: dict = {}
    if body is not None:
        if body.results is not None:
            kwargs["results"] = body.results
        if body.conclusion is not None:
            kwargs["conclusion"] = body.conclusion
        if body.recommendation is not None:
            kwargs["recommendation"] = body.recommendation
    experiment = await gtm_service.complete_experiment(db, eid, **kwargs)
    await db.commit()
    return {"data": _experiment_to_dict(experiment)}


@router.delete("/{experiment_id}")
async def delete_experiment(
    experiment_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete an experiment. Admin only."""
    _requi[RESEND_KEY_REDACTED](current_user)
    eid = _parse_uuid(experiment_id)
    experiment = await gtm_service.soft_delete_experiment(db, eid)
    await db.commit()
    return {"data": {"id": str(experiment.id), "deleted": True}}
