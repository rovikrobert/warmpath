import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models.contact import Contact
from app.models.job import JobOpening
from app.models.match_result import IntroMessage, IntroRequest, MatchResult
from app.models.user import ConnectorProfile, User
from app.schemas.match import (
    IntroMessageResponse,
    IntroMessageUpdate,
    IntroRequestCreate,
    IntroRequestResponse,
)
from app.services.intro_drafter import (
    CLAUDE_MODEL as INTRO_MODEL,
    draft_referral_request,
)
from app.utils.security import get_current_user

router = APIRouter()


async def _load_intro_context(
    body: IntroRequestCreate, user_id: uuid.UUID, db: AsyncSession
) -> tuple[Contact, MatchResult | None, "JobOpening | None", ConnectorProfile | None]:
    """Load and validate the contact, match result, job opening, and profile."""
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == body.contact_id,
            Contact.user_id == user_id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = contact_result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    match_result = None
    if body.match_result_id:
        mr_result = await db.execute(
            select(MatchResult).where(
                MatchResult.id == body.match_result_id,
                MatchResult.user_id == user_id,
            )
        )
        match_result = mr_result.scalar_one_or_none()
        if match_result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match result not found",
            )

    job_opening = None
    if body.job_opening_id:
        jo_result = await db.execute(
            select(JobOpening).where(JobOpening.id == body.job_opening_id)
        )
        job_opening = jo_result.scalar_one_or_none()
        if job_opening is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job opening not found",
            )

    profile_result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == user_id)
    )
    connector_profile = profile_result.scalar_one_or_none()

    return contact, match_result, job_opening, connector_profile


@router.post("/intros", status_code=status.HTTP_201_CREATED)
async def create_intro(
    body: IntroRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create an intro request and generate referral message drafts."""
    contact, match_result, job_opening, connector_profile = (
        await _load_intro_context(body, current_user.id, db)
    )

    # Create intro request
    intro_req = IntroRequest(
        user_id=current_user.id,
        contact_id=body.contact_id,
        match_result_id=body.match_result_id,
        job_opening_id=body.job_opening_id,
        context=body.context,
        tone=body.tone,
        channel=body.channel,
        status="generating",
    )
    db.add(intro_req)
    await db.flush()

    # Generate message drafts
    drafts = await draft_referral_request(
        contact=contact,
        user_profile=connector_profile,
        match_result=match_result,
        job_opening=job_opening,
        channel=body.channel,
    )

    model_version = "mock-v1" if settings.AI_MOCK_MODE else INTRO_MODEL

    for draft in drafts:
        msg = IntroMessage(
            intro_request_id=intro_req.id,
            variant_label=draft.variant_label,
            subject_line=draft.subject_line,
            message_body=draft.message_body,
            sequence_step=draft.sequence_step,
            step_label=draft.step_label,
            send_after_days=draft.send_after_days,
            coaching_notes=draft.coaching_notes,
            is_selected=False,
            ai_model_version=model_version,
        )
        db.add(msg)

    intro_req.status = "completed"

    # Track funnel step
    from app.utils.tracking import track_action

    await track_action(
        db, current_user.id, "intro_draft",
        resource_id=intro_req.id,
        metadata_={"contact_id": str(body.contact_id), "channel": body.channel},
    )

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


@router.get("/intros/pending")
async def get_pending_intros(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    days_lookahead: int = Query(default=0, ge=0),
) -> dict:
    """Return intro messages that are due to be sent.

    A message is "due" when the number of days since the intro_request was
    created is >= the message's send_after_days.
    """
    result = await db.execute(
        select(IntroRequest)
        .options(selectinload(IntroRequest.intro_messages))
        .where(
            IntroRequest.user_id == current_user.id,
            IntroRequest.status == "completed",
        )
    )
    intro_reqs = result.scalars().all()

    now = datetime.now(timezone.utc)
    pending_messages: list[dict] = []

    for req in intro_reqs:
        for msg in req.intro_messages:
            send_after = msg.send_after_days or 0
            created = req.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            due_date = created + timedelta(days=send_after)
            lookahead_date = now + timedelta(days=days_lookahead)
            if due_date <= lookahead_date:
                msg_resp = IntroMessageResponse.model_validate(msg).model_dump(
                    mode="json"
                )
                msg_resp["intro_request_id"] = str(req.id)
                msg_resp["contact_id"] = str(req.contact_id)
                msg_resp["due_date"] = due_date.isoformat()
                pending_messages.append(msg_resp)

    return {
        "data": pending_messages,
        "meta": {"count": len(pending_messages)},
    }


@router.get("/intros/{intro_id}")
async def get_intro(
    intro_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve an intro request with its generated messages."""
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
    """Update an intro message's selection state or edited body."""
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

    resp_data = IntroMessageResponse.model_validate(msg).model_dump(mode="json")
    meta: dict = {}

    # When a message is selected, suggest tracking as an application
    if body.is_selected:
        # Reload intro request to get contact/company info
        ir_result = await db.execute(
            select(IntroRequest).where(IntroRequest.id == intro_id)
        )
        ir = ir_result.scalar_one()
        contact_result = await db.execute(
            select(Contact).where(
                Contact.id == ir.contact_id,
                Contact.user_id == current_user.id,
            )
        )
        contact = contact_result.scalar_one_or_none()
        meta["suggest_track"] = True
        meta["prefilled_application"] = {
            "company_name": contact.current_company if contact else "Unknown",
            "contact_id": str(ir.contact_id),
            "job_opening_id": str(ir.job_opening_id) if ir.job_opening_id else None,
            "match_result_id": str(ir.match_result_id) if ir.match_result_id else None,
            "channel": ir.channel,
        }

    return {
        "data": resp_data,
        "meta": meta,
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
        job_opening_id=intro_req.job_opening_id,
        context=intro_req.context,
        tone=intro_req.tone,
        channel=intro_req.channel,
        status=intro_req.status,
        messages=messages,
        created_at=intro_req.created_at,
    ).model_dump(mode="json")
    return resp
