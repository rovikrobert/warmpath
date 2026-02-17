import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.contact import Contact
from app.models.company import Company
from app.models.job import Application, JobOpening
from app.models.match_result import IntroRequest, MatchResult
from app.models.user import User
from app.schemas.application import (
    VALID_STATUSES,
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatsResponse,
    ApplicationUpdate,
)
from app.utils.security import get_current_user

router = APIRouter()


def _make_tz_aware(dt: datetime | None) -> datetime | None:
    """Ensure datetime is timezone-aware (SQLite stores naive)."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _enrich_response(app: Application, now: datetime) -> dict:
    """Build ApplicationResponse dict from an Application ORM instance."""
    sent_at = _make_tz_aware(app.sent_at)
    responded_at = _make_tz_aware(app.responded_at)
    follow_up_at = _make_tz_aware(app.follow_up_at)
    created_at = _make_tz_aware(app.created_at)

    # Compute days_since_sent
    days_since_sent = None
    if sent_at:
        days_since_sent = (now - sent_at).days

    # Compute needs_follow_up
    needs_follow_up = False
    if app.status == "message_sent" and responded_at is None:
        if follow_up_at and follow_up_at <= now:
            needs_follow_up = True
        elif sent_at and days_since_sent is not None and days_since_sent >= 7:
            needs_follow_up = True

    # Contact name
    contact_name = None
    if app.contact:
        contact_name = app.contact.full_name

    # Company info
    company_info = None
    if app.company:
        company_info = {
            "id": str(app.company.id),
            "name": app.company.name,
            "domain": app.company.domain,
            "industry": app.company.industry,
        }

    # Job opening title
    job_opening_title = None
    if app.job_opening:
        job_opening_title = app.job_opening.title

    return ApplicationResponse(
        id=app.id,
        user_id=app.user_id,
        company_name=app.company_name,
        role_title=app.role_title,
        status=app.status,
        channel=app.channel,
        contact_id=app.contact_id,
        job_opening_id=app.job_opening_id,
        match_result_id=app.match_result_id,
        company_id=app.company_id,
        notes=app.notes,
        sent_at=sent_at,
        responded_at=responded_at,
        follow_up_at=follow_up_at,
        created_at=created_at or app.created_at,
        updated_at=_make_tz_aware(app.updated_at) or app.updated_at,
        contact_name=contact_name,
        company_info=company_info,
        job_opening_title=job_opening_title,
        days_since_sent=days_since_sent,
        needs_follow_up=needs_follow_up,
    ).model_dump(mode="json")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_application(
    body: ApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a new job application."""
    # Validate contact belongs to user if provided
    if body.contact_id:
        contact_result = await db.execute(
            select(Contact).where(
                Contact.id == body.contact_id,
                Contact.user_id == current_user.id,
                Contact.deleted_at.is_(None),
            )
        )
        if contact_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Contact not found",
            )

    # Validate job opening if provided
    if body.job_opening_id:
        jo_result = await db.execute(
            select(JobOpening).where(JobOpening.id == body.job_opening_id)
        )
        if jo_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Job opening not found",
            )

    # Validate match result belongs to user if provided
    if body.match_result_id:
        mr_result = await db.execute(
            select(MatchResult).where(
                MatchResult.id == body.match_result_id,
                MatchResult.user_id == current_user.id,
            )
        )
        if mr_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Match result not found",
            )

    # Try to find company by name for linking
    company_id = None
    company_result = await db.execute(
        select(Company).where(func.lower(Company.name) == body.company_name.lower())
    )
    company = company_result.scalar_one_or_none()
    if company:
        company_id = company.id

    app_record = Application(
        user_id=current_user.id,
        company_name=body.company_name,
        role_title=body.role_title,
        contact_id=body.contact_id,
        job_opening_id=body.job_opening_id,
        match_result_id=body.match_result_id,
        company_id=company_id,
        channel=body.channel,
        notes=body.notes,
        status="draft",
    )
    db.add(app_record)
    await db.commit()
    await db.refresh(app_record)

    # Eagerly load relationships for response
    app_record = await _load_application(db, app_record.id, current_user.id)

    now = datetime.now(timezone.utc)
    return {
        "data": _enrich_response(app_record, now),
        "meta": {},
    }


@router.get("")
async def list_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status"),
    company: str | None = Query(default=None),
    needs_follow_up: bool | None = Query(default=None),
    sort: str = Query(default="created_at"),
) -> dict:
    """List all applications for the current user with optional filters."""
    query = select(Application).where(
        Application.user_id == current_user.id,
        Application.deleted_at.is_(None),
    )

    if status_filter:
        query = query.where(Application.status == status_filter)

    if company:
        query = query.where(
            func.lower(Application.company_name).contains(company.lower())
        )

    # Sort
    sort_column = {
        "created_at": Application.created_at,
        "sent_at": Application.sent_at,
        "follow_up_at": Application.follow_up_at,
        "status": Application.status,
    }.get(sort, Application.created_at)

    query = query.order_by(sort_column.desc().nullslast())

    # Eager-load relationships in one query (avoids N+1)
    query = query.options(
        selectinload(Application.contact),
        selectinload(Application.company),
        selectinload(Application.job_opening),
    )

    result = await db.execute(query)
    apps = result.scalars().all()

    now = datetime.now(timezone.utc)
    response_list = []

    for app_record in apps:
        enriched = _enrich_response(app_record, now)
        response_list.append(enriched)

    # Filter by needs_follow_up after enrichment (computed field)
    if needs_follow_up is not None:
        response_list = [
            a for a in response_list if a["needs_follow_up"] == needs_follow_up
        ]

    return {
        "data": response_list,
        "meta": {"count": len(response_list)},
    }


@router.get("/stats")
async def get_application_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return aggregate application statistics for the current user."""
    result = await db.execute(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.deleted_at.is_(None),
        )
    )
    apps = result.scalars().all()

    total = len(apps)
    by_status: dict[str, int] = {}
    sent_count = 0
    responded_count = 0
    interview_count = 0
    response_days: list[float] = []
    channel_stats: dict[str, dict[str, int]] = {}

    for app_record in apps:
        by_status[app_record.status] = by_status.get(app_record.status, 0) + 1

        if app_record.status != "draft":
            sent_count += 1

        if app_record.status in (
            "responded",
            "interview_scheduled",
            "interviewed",
            "offer_received",
            "offer_accepted",
        ):
            responded_count += 1

        if app_record.status in (
            "interview_scheduled",
            "interviewed",
            "offer_received",
            "offer_accepted",
        ):
            interview_count += 1

        # Response time calculation
        if app_record.sent_at and app_record.responded_at:
            sent = _make_tz_aware(app_record.sent_at)
            resp = _make_tz_aware(app_record.responded_at)
            if sent and resp:
                response_days.append((resp - sent).total_seconds() / 86400)

        # Channel tracking
        ch = app_record.channel or "unknown"
        if ch not in channel_stats:
            channel_stats[ch] = {"sent": 0, "responded": 0}
        if app_record.status != "draft":
            channel_stats[ch]["sent"] += 1
        if app_record.status in (
            "responded",
            "interview_scheduled",
            "interviewed",
            "offer_received",
            "offer_accepted",
        ):
            channel_stats[ch]["responded"] += 1

    response_rate = responded_count / sent_count if sent_count > 0 else 0.0
    interview_rate = interview_count / sent_count if sent_count > 0 else 0.0
    avg_days = (
        round(sum(response_days) / len(response_days), 1) if response_days else None
    )

    # Best channel by response rate
    best_channel = None
    best_rate = 0.0
    for ch, stats in channel_stats.items():
        if stats["sent"] > 0:
            rate = stats["responded"] / stats["sent"]
            if rate > best_rate:
                best_rate = rate
                best_channel = ch

    return {
        "data": ApplicationStatsResponse(
            total=total,
            by_status=by_status,
            response_rate=round(response_rate, 3),
            interview_rate=round(interview_rate, 3),
            avg_days_to_response=avg_days,
            best_channel=best_channel,
        ).model_dump(),
        "meta": {},
    }


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve a single application by ID."""
    app_record = await _load_application(db, application_id, current_user.id)
    if app_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    now = datetime.now(timezone.utc)
    return {
        "data": _enrich_response(app_record, now),
        "meta": {},
    }


@router.patch("/{application_id}")
async def update_application(
    application_id: uuid.UUID,
    body: ApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an application's status, notes, or follow-up date."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
            Application.deleted_at.is_(None),
        )
    )
    app_record = result.scalar_one_or_none()
    if app_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    now = datetime.now(timezone.utc)

    if body.status is not None:
        if body.status not in VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid status. Must be one of: {sorted(VALID_STATUSES)}",
            )
        old_status = app_record.status
        app_record.status = body.status

        # Auto-set sent_at when transitioning to message_sent
        if body.status == "message_sent" and old_status == "draft":
            app_record.sent_at = now

        # Auto-set responded_at when transitioning to responded
        if body.status == "responded" and app_record.responded_at is None:
            app_record.responded_at = now

    if body.notes is not None:
        app_record.notes = body.notes

    if body.follow_up_at is not None:
        app_record.follow_up_at = body.follow_up_at

    if body.responded_at is not None:
        app_record.responded_at = body.responded_at

    # Track funnel step
    from app.models.enrichment import UsageLog

    db.add(UsageLog(
        user_id=current_user.id,
        action="application_update",
        metadata_={"application_id": str(application_id), "new_status": body.status},
    ))

    await db.commit()

    app_record = await _load_application(db, application_id, current_user.id)
    return {
        "data": _enrich_response(app_record, now),
        "meta": {},
    }


@router.delete("/{application_id}")
async def delete_application(
    application_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete an application."""
    result = await db.execute(
        select(Application).where(
            Application.id == application_id,
            Application.user_id == current_user.id,
            Application.deleted_at.is_(None),
        )
    )
    app_record = result.scalar_one_or_none()
    if app_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found",
        )

    app_record.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    return {"data": {"deleted": True}, "meta": {}}


@router.post("/from-intro/{intro_id}", status_code=status.HTTP_201_CREATED)
async def create_from_intro(
    intro_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create an application pre-filled from an intro request."""
    result = await db.execute(
        select(IntroRequest).where(
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

    # Load contact for company name (scoped to user's vault)
    contact_result = await db.execute(
        select(Contact).where(
            Contact.id == intro_req.contact_id,
            Contact.user_id == current_user.id,
        )
    )
    contact = contact_result.scalar_one_or_none()

    company_name = "Unknown"
    company_id = None
    role_title = None
    channel = intro_req.channel

    if contact and contact.current_company:
        company_name = contact.current_company
        # Try to link to company record
        if contact.company_id:
            company_id = contact.company_id

    # Load job opening for role title
    if intro_req.job_opening_id:
        jo_result = await db.execute(
            select(JobOpening).where(JobOpening.id == intro_req.job_opening_id)
        )
        jo = jo_result.scalar_one_or_none()
        if jo:
            role_title = jo.title

    app_record = Application(
        user_id=current_user.id,
        company_name=company_name,
        role_title=role_title,
        contact_id=intro_req.contact_id,
        job_opening_id=intro_req.job_opening_id,
        match_result_id=intro_req.match_result_id,
        company_id=company_id,
        channel=channel,
        status="draft",
    )
    db.add(app_record)
    await db.commit()
    await db.refresh(app_record)

    app_record = await _load_application(db, app_record.id, current_user.id)
    now = datetime.now(timezone.utc)
    return {
        "data": _enrich_response(app_record, now),
        "meta": {},
    }


async def _load_application(
    db: AsyncSession, app_id: uuid.UUID, user_id: uuid.UUID
) -> Application | None:
    """Load application with eagerly loaded relationships."""
    from sqlalchemy.orm import selectinload

    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.contact),
            selectinload(Application.company),
            selectinload(Application.job_opening),
        )
        .where(
            Application.id == app_id,
            Application.user_id == user_id,
            Application.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
