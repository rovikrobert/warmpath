import base64
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.rate_limit import check_rate_limit
from app.models.contact import Contact, CsvUpload
from app.models.match_result import WarmScore
from app.models.user import User
from app.schemas.contact import (
    ContactResponse,
    ContactUpdate,
    CsvUploadResponse,
    ManualContactBulkCreate,
    ManualContactCreate,
    PaginationMeta,
)
from app.services.company_normalizer import link_contact_to_company
from app.services.csv_parser import generate_fingerprint, parse_linkedin_csv
from app.services.warm_scorer import batch_compute_scores
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user

router = APIRouter()


def _contact_to_response(contact: Contact, warm_score_val: float | None = None) -> dict:
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    if warm_score_val is not None:
        resp["warm_score"] = warm_score_val
    return resp


MAX_CSV_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CSV_CONTENT_TYPES = {"text/csv", "application/octet-stream"}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Rate limit check
    allowed, count = await check_rate_limit(
        current_user.id, "csv_upload", settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY, db
    )
    if not allowed:
        raise RateLimitError(
            f"CSV upload limit reached ({settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY}/day)"
        )

    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted",
        )

    # Content-type validation
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content type '{file.content_type}' is not supported. "
            "Upload a CSV file (text/csv).",
        )

    # File size limit — read with cap
    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_CSV_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"CSV file exceeds the maximum allowed size of "
            f"{MAX_CSV_FILE_SIZE // (1024 * 1024)} MB.",
        )

    # Validate CSV is parseable before queuing (also enforces row limit + encoding)
    try:
        parse_linkedin_csv(raw_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Failed to parse CSV: {exc}",
        ) from exc

    # Base64-encode for safe serialization
    content_b64 = base64.b64encode(raw_bytes).decode("ascii")

    # Create csv_upload record
    csv_upload = CsvUpload(
        user_id=current_user.id,
        filename=file.filename,
        file_size_bytes=len(raw_bytes),
        status="queued",
    )
    db.add(csv_upload)
    await db.flush()

    if settings.CSV_ASYNC_PROCESSING:
        # Commit so the Celery worker can see the row, then dispatch
        await db.commit()
        from app.tasks.csv_processing import process_csv_upload

        process_csv_upload.delay(str(csv_upload.id), str(current_user.id), content_b64)
    else:
        # Inline processing (tests, or when no Redis available)
        from app.tasks.csv_processing import process_csv_upload_core

        await process_csv_upload_core(
            str(csv_upload.id), str(current_user.id), content_b64, db
        )

    await db.commit()
    await db.refresh(csv_upload)

    return {
        "data": CsvUploadResponse.model_validate(csv_upload).model_dump(mode="json"),
        "meta": {},
    }


@router.get("/uploads/{upload_id}")
async def get_upload_status(
    upload_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Poll the status of a CSV upload."""
    result = await db.execute(
        select(CsvUpload).where(
            CsvUpload.id == upload_id,
            CsvUpload.user_id == current_user.id,
        )
    )
    csv_upload = result.scalar_one_or_none()
    if csv_upload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Upload not found",
        )

    return {
        "data": CsvUploadResponse.model_validate(csv_upload).model_dump(mode="json"),
        "meta": {},
    }


@router.post("/compute-scores")
async def compute_scores(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Trigger batch recomputation of warm scores for all contacts."""
    scores = await batch_compute_scores(current_user.id, db)
    await db.commit()
    return {
        "data": {"scores_computed": len(scores)},
        "meta": {},
    }


@router.get("")
async def list_contacts(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    search: str | None = Query(None),
    relationship_type: str | None = Query(None),
    source: str | None = Query(None),
    sort_by: str = Query(
        "created_at",
        pattern="^(full_name|current_company|connected_on|created_at|warm_score)$",
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Join contacts with warm_scores to include score in response
    base_query = (
        select(Contact, WarmScore.total_score)
        .outerjoin(
            WarmScore,
            (WarmScore.contact_id == Contact.id)
            & (WarmScore.user_id == Contact.user_id),
        )
        .where(
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )

    if search:
        pattern = f"%{search}%"
        base_query = base_query.where(
            Contact.full_name.ilike(pattern)
            | Contact.current_company.ilike(pattern)
            | Contact.current_title.ilike(pattern)
            | Contact.email.ilike(pattern)
        )

    if relationship_type:
        base_query = base_query.where(Contact.relationship_type == relationship_type)

    if source:
        base_query = base_query.where(Contact.source == source)

    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total = (await db.execute(count_query)).scalar() or 0

    # Sort
    if sort_by == "warm_score":
        sort_col = WarmScore.total_score
        if sort_order == "desc":
            # nulls last when sorting desc
            sort_col = sort_col.desc().nullslast()
        else:
            sort_col = sort_col.asc().nullsfirst()
        base_query = base_query.order_by(sort_col)
    else:
        sort_column = getattr(Contact, sort_by)
        if sort_order == "desc":
            sort_column = sort_column.desc()
        base_query = base_query.order_by(sort_column)

    # Paginate
    offset = (page - 1) * per_page
    base_query = base_query.offset(offset).limit(per_page)

    result = await db.execute(base_query)
    rows = result.all()

    data = []
    for contact, score_val in rows:
        resp = ContactResponse.model_validate(contact).model_dump(mode="json")
        resp["warm_score"] = float(score_val) if score_val is not None else None
        data.append(resp)

    return {
        "data": data,
        "meta": PaginationMeta(
            page=page,
            per_page=per_page,
            total=total,
            total_pages=max(1, math.ceil(total / per_page)),
        ).model_dump(),
    }


@router.get("/{contact_id}")
async def get_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Contact, WarmScore.total_score)
        .outerjoin(
            WarmScore,
            (WarmScore.contact_id == Contact.id)
            & (WarmScore.user_id == Contact.user_id),
        )
        .where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    contact, score_val = row
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    resp["warm_score"] = float(score_val) if score_val is not None else None
    return {
        "data": resp,
        "meta": {},
    }


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: uuid.UUID,
    body: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update a contact's relationship_type, how_you_know, or notes."""
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )

    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(contact, key, value)

    await db.commit()
    await db.refresh(contact)

    return {
        "data": ContactResponse.model_validate(contact).model_dump(mode="json"),
        "meta": {},
    }


@router.delete("/{contact_id}", status_code=status.HTTP_200_OK)
async def delete_contact(
    contact_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.user_id == current_user.id,
            Contact.deleted_at.is_(None),
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Contact not found",
        )
    contact.deleted_at = datetime.now(timezone.utc)
    await db.commit()
    return {
        "data": {"id": str(contact.id), "deleted": True},
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Manual contacts import
# ---------------------------------------------------------------------------


async def _create_manual_contact(
    data: ManualContactCreate,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> Contact:
    """Create a single manual contact and link to company."""
    full_name = f"{data.first_name.strip()} {data.last_name.strip()}"
    fingerprint = generate_fingerprint(full_name, data.company, None)

    # Check for duplicate
    if fingerprint:
        existing_result = await db.execute(
            select(Contact).where(
                Contact.user_id == user_id,
                Contact.fingerprint == fingerprint,
                Contact.deleted_at.is_(None),
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Contact '{full_name}' already exists",
            )

    contact = Contact(
        user_id=user_id,
        first_name=data.first_name.strip().title(),
        last_name=data.last_name.strip().title(),
        full_name=full_name.strip().title(),
        email=data.email,
        current_title=data.position,
        current_company=data.company,
        location=data.location,
        relationship_type=data.relationship_type,
        how_you_know=data.how_you_know,
        last_interaction_date=data.last_interaction_date,
        connected_on=data.last_interaction_date,
        fingerprint=fingerprint,
        source="manual",
    )
    db.add(contact)
    await db.flush()
    await link_contact_to_company(contact, db)
    return contact


@router.post("/manual", status_code=status.HTTP_201_CREATED)
async def create_manual_contact(
    body: ManualContactCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create a single manual contact."""
    contact = await _create_manual_contact(body, current_user.id, db)

    # Recompute scores to include the new contact
    await batch_compute_scores(current_user.id, db)
    await db.commit()
    await db.refresh(contact)

    return {
        "data": ContactResponse.model_validate(contact).model_dump(mode="json"),
        "meta": {},
    }


@router.post("/manual/bulk", status_code=status.HTTP_201_CREATED)
async def create_manual_contacts_bulk(
    body: ManualContactBulkCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Bulk create manual contacts (up to 50)."""
    created = []
    errors = []
    for i, item in enumerate(body.contacts):
        try:
            contact = await _create_manual_contact(item, current_user.id, db)
            created.append(contact)
        except HTTPException as exc:
            errors.append({"index": i, "detail": exc.detail})

    if created:
        await batch_compute_scores(current_user.id, db)

    await db.commit()

    return {
        "data": {
            "created": len(created),
            "errors": errors,
        },
        "meta": {},
    }
