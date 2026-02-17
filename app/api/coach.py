"""Keevs AI Job Coach endpoints — briefing, chat, and streaming chat."""

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UsageLog
from app.models.user import User
from ops_team.keevs.coach_service import (
    _assemble_context,
    generate_briefing,
    generate_chat_response,
    generate_chat_response_stream,
)
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-user concurrent SSE connection tracking
_active_streams: dict[str, int] = defaultdict(int)
_MAX_CONCURRENT_STREAMS = 3
_SSE_TIMEOUT_SECONDS = 120


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
    # Track funnel step
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_briefing",
            resource_type="coach",
        )
    )
    await db.commit()

    data = await generate_briefing(current_user.id, db)
    return {"data": data, "meta": {}}


@router.post("/chat")
async def coach_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a message to Keevs and get a response."""
    # Track funnel step
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_chat",
            resource_type="coach",
            metadata_={"message_length": len(body.message), "streaming": False},
        )
    )
    await db.commit()

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
    user_key = str(current_user.id)

    # Enforce per-user concurrent stream limit
    if _active_streams[user_key] >= _MAX_CONCURRENT_STREAMS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent streams. Please wait for an existing stream to finish.",
        )

    # Always use server-assembled context (ignore client-supplied context_snapshot)
    context = await _assemble_context(current_user.id, db)

    # Sanitize conversation history
    history = _sanitize_conversation_history(body.conversation_history)

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
        _active_streams[user_key] += 1
        deadline = asyncio.get_event_loop().time() + _SSE_TIMEOUT_SECONDS
        try:
            async for chunk in generate_chat_response_stream(
                body.message, history, context
            ):
                if asyncio.get_event_loop().time() > deadline:
                    logger.warning("SSE stream timed out for user %s", user_key)
                    break
                yield f"data: {json.dumps({'t': chunk})}\n\n"
        except asyncio.CancelledError:
            logger.info(
                "SSE stream cancelled (client disconnect) for user %s", user_key
            )
        finally:
            _active_streams[user_key] -= 1
            if _active_streams[user_key] <= 0:
                _active_streams.pop(user_key, None)
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _sanitize_conversation_history(
    history: list[dict[str, Any]] | None,
) -> list[dict]:
    """Validate and sanitize conversation history entries."""
    if not history:
        return []
    sanitized: list[dict] = []
    for entry in history[-10:]:  # Cap at 10 entries
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in ("user", "keevs") or not isinstance(content, str):
            continue
        sanitized.append({"role": role, "content": content[:5000]})
    return sanitized
