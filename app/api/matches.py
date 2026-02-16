import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.contact import Contact
from app.models.match_result import IntroMessage, IntroRequest, MatchResult
from app.models.user import ConnectorProfile, User
from app.schemas.match import (
    IntroMessageResponse,
    IntroMessageUpdate,
    IntroRequestCreate,
    IntroRequestResponse,
)
from app.services.intro_drafter import CLAUDE_MODEL as INTRO_MODEL, draft_intro
from app.utils.security import get_current_user

router = APIRouter()


@router.post("/intros", status_code=status.HTTP_201_CREATED)
async def create_intro(
    body: IntroRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify contact belongs to user
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == body.contact_id,
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    # Optionally verify match_result belongs to user
    match_result = None
    if body.match_result_id:
        mr_result = await db.execute(
            select(MatchResult).where(
                MatchResult.id == body.match_result_id,
                MatchResult.user_id == current_user.id,
            )
        )
        match_result = mr_result.scalar_one_or_none()
        if match_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match result not found",
            )

    # Load connector profile for context
    profile_result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == current_user.id)
    )
    connector_profile = profile_result.scalar_one_or_none()

    # Create intro request
    intro_req = IntroRequest(
        user_id=current_user.id,
        contact_id=body.contact_id,
        match_result_id=body.match_result_id,
        context=body.context,
        tone=body.tone,
        channel=body.channel,
        status="generating",
    )
    db.add(intro_req)
    await db.flush()

    # Generate message drafts
    drafts = await draft_intro(
        contact=contact,
        connector_profile=connector_profile,
        match_result=match_result,
        tone=body.tone,
        channel=body.channel,
    )

    model_version = "mock-v1" if settings.AI_MOCK_MODE else INTRO_MODEL

    for draft in drafts:
        msg = IntroMessage(
            intro_request_id=intro_req.id,
            variant_label=draft.variant_label,
            subject_line=draft.subject_line,
            message_body=draft.message_body,
            is_selected=False,
            ai_model_version=model_version,
        )
        db.add(msg)

    intro_req.status = "completed"
    await db.commit()

    # Reload with messages
    result = await db.execute(
        select(IntroRequest)
        .options(selectinload(IntroRequest.intro_messages))
        .where(IntroRequest.id == intro_req.id)
    )
    intro_req = result.scalar_one()

    return {
        "data": _intro_to_response(intro_req),
        "meta": {},
    }


@router.get("/intros/{intro_id}")
async def get_intro(
    intro_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(IntroRequest)
        .options(selectinload(IntroRequest.intro_messages))
        .where(
            IntroRequest.id == intro_id,
            IntroRequest.user_id == current_user.id,
        )
    )
    intro_req = result.scalar_one_or_none()
    if intro_req is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intro request not found",
        )

    return {
        "data": _intro_to_response(intro_req),
        "meta": {},
    }


@router.patch("/intros/{intro_id}/messages/{message_id}")
async def update_message(
    intro_id: uuid.UUID,
    message_id: uuid.UUID,
    body: IntroMessageUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Verify intro request belongs to user
    intro_result = await db.execute(
        select(IntroRequest).where(
            IntroRequest.id == intro_id,
            IntroRequest.user_id == current_user.id,
        )
    )
    if intro_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Intro request not found",
        )

    # Get the message
    msg_result = await db.execute(
        select(IntroMessage).where(
            IntroMessage.id == message_id,
            IntroMessage.intro_request_id == intro_id,
        )
    )
    msg = msg_result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    if body.is_selected is not None:
        msg.is_selected = body.is_selected
    if body.user_edited_body is not None:
        msg.user_edited_body = body.user_edited_body

    await db.commit()
    await db.refresh(msg)

    return {
        "data": IntroMessageResponse.model_validate(msg).model_dump(mode="json"),
        "meta": {},
    }


def _intro_to_response(intro_req: IntroRequest) -> dict:
    """Convert IntroRequest + messages to response dict."""
    messages = [
        IntroMessageResponse.model_validate(m).model_dump(mode="json")
        for m in intro_req.intro_messages
    ]
    resp = IntroRequestResponse(
        id=intro_req.id,
        user_id=intro_req.user_id,
        contact_id=intro_req.contact_id,
        match_result_id=intro_req.match_result_id,
        context=intro_req.context,
        tone=intro_req.tone,
        channel=intro_req.channel,
        status=intro_req.status,
        messages=messages,
        created_at=intro_req.created_at,
    ).model_dump(mode="json")
    return resp
