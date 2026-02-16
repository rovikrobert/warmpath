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
from app.schemas.contact import ContactResponse, CsvUploadResponse, PaginationMeta
from app.services.csv_parser import parse_linkedin_csv
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user

router = APIRouter()


def _contact_to_response(contact: Contact, warm_sco[RESEND_KEY_REDACTED]: float | None = None) -> dict:
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    if warm_sco[RESEND_KEY_REDACTED] is not None:
        resp["warm_score"] = warm_sco[RESEND_KEY_REDACTED]
    return resp


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

    raw_bytes = await file.read()

    # Validate CSV is parseable before queuing
    try:
        parse_linkedin_csv(raw_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
    from app.services.warm_scorer import batch_compute_scores

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
    for contact, sco[RESEND_KEY_REDACTED] in rows:
        resp = ContactResponse.model_validate(contact).model_dump(mode="json")
        resp["warm_score"] = float(sco[RESEND_KEY_REDACTED]) if sco[RESEND_KEY_REDACTED] is not None else None
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
    contact, sco[RESEND_KEY_REDACTED] = row
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    resp["warm_score"] = float(sco[RESEND_KEY_REDACTED]) if sco[RESEND_KEY_REDACTED] is not None else None
    return {
        "data": resp,
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
