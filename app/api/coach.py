"""Keevs AI Job Coach endpoints — briefing, chat, and streaming chat."""

import json
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UsageLog
from app.models.user import User
from app.services.coach import (
    _assemble_context,
    generate_briefing,
    generate_chat_response,
    generate_chat_response_stream,
)
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


@router.post("/chat/stream")
async def coach_chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream a chat response from Keevs via Server-Sent Events."""
    # Resolve context before streaming (needs DB session)
    context = body.context_snapshot or await _assemble_context(current_user.id, db)

    # Log usage eagerly (captured even if client disconnects mid-stream)
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_chat",
            resource_type="coach",
            metadata_={"message_length": len(body.message), "streaming": True},
        )
    )
    await db.commit()

    async def event_stream():
        async for chunk in generate_chat_response_stream(
            body.message, body.conversation_history or [], context
        ):
            yield f"data: {json.dumps({'t': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
