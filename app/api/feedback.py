"""Feedback API — collect user thumbs-up/down on features.

Endpoints:
  POST   /feedback  — submit feedback (thumbs up/down + optional comment)
"""

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UserFeedback
from app.models.user import User
from app.utils.security import get_current_user

router = APIRouter()


class FeedbackRequest(BaseModel):
    feature: str = Field(..., min_length=1, max_length=100)
    rating: int = Field(..., ge=-1, le=1)  # -1 down, 0 neutral, 1 up
    resource_id: uuid.UUID | None = None
    comment: str | None = Field(None, max_length=1000)


@router.post("")
async def submit_feedback(
    body: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit feedback on a feature (search results, intro, coaching, etc.)."""
    fb = UserFeedback(
        user_id=current_user.id,
        feature=body.feature,
        rating=body.rating,
        resource_id=body.resource_id,
        comment=body.comment,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)

    return {
        "data": {
            "id": str(fb.id),
            "feature": fb.feature,
            "rating": fb.rating,
        },
        "meta": {},
    }
