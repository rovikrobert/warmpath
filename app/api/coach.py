"""Keevs AI Job Coach endpoints — briefing and chat."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.coach import generate_briefing, generate_chat_response
from app.utils.security import get_current_user

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[dict[str, Any]] | None = None
    context_snapshot: dict[str, Any] | None = None


@router.get("/briefing")
async def coach_briefing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a personalized daily briefing from Keevs."""
    data = await generate_briefing(current_user.id, db)
    return {"data": data, "meta": {}}


@router.post("/chat")
async def coach_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a message to Keevs and get a response."""
    data = await generate_chat_response(
        user_id=current_user.id,
        message=body.message,
        conversation_history=body.conversation_history,
        context_snapshot=body.context_snapshot,
        db=db,
    )
    return {"data": data, "meta": {}}
