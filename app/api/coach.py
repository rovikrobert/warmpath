"""Coach endpoints — persona-routed briefing, chat, and streaming chat.

Routes persona to Keevs (job seekers) or Treb (network holders) based on
user intent and message topic detection.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.enrichment import UsageLog
from app.models.user import User
from app.utils.performance import timed
from ops_team.keevs.coach_service import (
    _assemble_context,
    _detect_topic,
    _get_or_create_session,
    _record_topic,
    generate_briefing,
    generate_chat_response,
    generate_chat_response_stream,
    is_contact_search_query,
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


def _resolve_persona(user: User, message: str | None = None) -> str:
    """Determine which coach persona to use based on intent and message topic."""
    intent = getattr(user, "intent", None)
    if intent == "sha[RESEND_KEY_REDACTED]":
        return "treb"
    if intent == "find_referrals":
        return "keevs"
    # For explore users, auto-route by topic
    if intent == "explore" and message:
        from ops_team.treb.treb_coach_service import is_nh_topic

        if is_nh_topic(message):
            return "treb"
    return "keevs"


async def _run_contact_search_if_needed(user_id, message: str, db) -> dict | None:
    """Run NLP contact search if the message looks like a contact query."""
    if not is_contact_search_query(message):
        return None
    from app.services.nlp_contact_search import search_user_contacts
    from app.utils.tracking import track_action

    search_result = await search_user_contacts(user_id, message, db, limit=10)
    if search_result["total_matched"] > 0:
        await track_action(
            db,
            user_id,
            "coach_contact_search",
            metadata_={
                "query": message,
                "total_matched": search_result["total_matched"],
            },
        )
        return search_result
    return None


@router.get("/briefing")
@timed("coach_briefing")
async def coach_briefing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a personalized daily briefing from Keevs or Treb."""
    persona = _resolve_persona(current_user)

    # Track funnel step
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_briefing",
            resource_type="coach",
            metadata_={"persona": persona},
        )
    )
    await db.commit()

    if persona == "treb":
        from ops_team.treb.treb_coach_service import generate_nh_briefing

        data = await generate_nh_briefing(current_user.id, db)
    else:
        data = await generate_briefing(current_user.id, db)

    data["persona"] = persona
    return {"data": data, "meta": {}}


@router.post("/chat")
@timed("coach_chat")
async def coach_chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a message to Keevs or Treb and get a response."""
    persona = _resolve_persona(current_user, body.message)

    # Track funnel step
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_chat",
            resource_type="coach",
            metadata_={
                "message_length": len(body.message),
                "streaming": False,
                "persona": persona,
            },
        )
    )
    await db.commit()

    # Run contact search before generating response
    contact_results = await _run_contact_search_if_needed(
        current_user.id, body.message, db
    )

    if persona == "treb":
        from ops_team.treb.treb_coach_service import generate_nh_chat_response

        data = await generate_nh_chat_response(
            user_id=current_user.id,
            message=body.message,
            conversation_history=body.conversation_history,
            context_snapshot=body.context_snapshot,
            db=db,
        )
    else:
        data = await generate_chat_response(
            user_id=current_user.id,
            message=body.message,
            conversation_history=body.conversation_history,
            context_snapshot=body.context_snapshot,
            db=db,
            contact_results=contact_results,
        )

    data["persona"] = persona
    return {"data": data, "meta": {}}


@router.post("/chat/stream")
async def coach_chat_stream(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream a chat response from Keevs or Treb via Server-Sent Events."""
    user_key = str(current_user.id)
    persona = _resolve_persona(current_user, body.message)

    # Enforce per-user concurrent stream limit
    if _active_streams[user_key] >= _MAX_CONCURRENT_STREAMS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many concurrent streams. Please wait for an existing stream to finish.",
        )

    # Sanitize conversation history
    history = _sanitize_conversation_history(body.conversation_history)

    # Log usage eagerly (captured even if client disconnects mid-stream)
    db.add(
        UsageLog(
            user_id=current_user.id,
            action="coach_chat",
            resource_type="coach",
            metadata_={
                "message_length": len(body.message),
                "streaming": True,
                "persona": persona,
            },
        )
    )
    await db.commit()

    # Track session for streaming (Issue 6.2)
    if persona == "treb":
        from ops_team.treb.treb_coach_service import (
            _assemble_nh_context,
            _detect_nh_topic,
            _get_or_create_nh_session,
            _record_nh_topic,
            generate_nh_chat_response_stream,
        )

        context = await _assemble_nh_context(current_user.id, db)
        session = await _get_or_create_nh_session(current_user.id, db, context)
        topic = _detect_nh_topic(body.message)
        if topic:
            await _record_nh_topic(session, topic, db)
        session.message_count += 1
        session.last_message_at = datetime.now(timezone.utc)
        await db.commit()

        stream_gen = generate_nh_chat_response_stream(body.message, history, context)
    else:
        # Run contact search only for Keevs (not relevant for Treb)
        contact_results = await _run_contact_search_if_needed(
            current_user.id, body.message, db
        )
        context = await _assemble_context(current_user.id, db)
        session = await _get_or_create_session(current_user.id, db, context)
        topic = _detect_topic(body.message)
        if topic:
            await _record_topic(session, topic, db)
        session.message_count += 1
        session.last_message_at = datetime.now(timezone.utc)
        await db.commit()

        stream_gen = generate_chat_response_stream(
            body.message, history, context, contact_results
        )

    async def event_stream():
        _active_streams[user_key] += 1
        deadline = asyncio.get_event_loop().time() + _SSE_TIMEOUT_SECONDS
        try:
            # Emit persona as first event
            yield f"data: {json.dumps({'persona': persona})}\n\n"
            async for chunk in stream_gen:
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
        if role not in ("user", "keevs", "treb") or not isinstance(content, str):
            continue
        sanitized.append({"role": role, "content": content[:5000]})
    return sanitized
