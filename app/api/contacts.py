import base64
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status

from app.utils.performance import timed
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
    NlpSearchRequest,
    PaginationMeta,
)
from app.services.company_normalizer import link_contact_to_company
from app.services.csv_parser import generate_fingerprint, parse_linkedin_csv
from app.services.warm_scorer import batch_compute_scores
from app.utils.encryption import compute_blind_index
from app.utils.exceptions import RateLimitError
from app.utils.security import get_current_user

router = APIRouter()


def _contact_to_response(contact: Contact, warm_sco[RESEND_KEY_REDACTED]: float | None = None) -> dict:
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    if warm_sco[RESEND_KEY_REDACTED] is not None:
        resp["warm_score"] = warm_sco[RESEND_KEY_REDACTED]
    return resp


MAX_CSV_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_CSV_CONTENT_TYPES = {"text/csv", "application/octet-stream"}


async def _validate_csv_file(file: UploadFile) -> bytes:
    """Validate CSV filename, content-type, size, and parseability. Returns raw bytes."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted",
        )

    ct = (file.content_type or "").split(";")[0].strip().lower()
    if ct and ct not in ALLOWED_CSV_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Content type '{file.content_type}' is not supported. "
            "Upload a CSV file (text/csv).",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) > MAX_CSV_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"CSV file exceeds the maximum allowed size of "
            f"{MAX_CSV_FILE_SIZE // (1024 * 1024)} MB.",
        )

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

    return raw_bytes


@router.post("/upload", status_code=status.HTTP_201_CREATED)
@timed("csv_upload_endpoint")
async def upload_csv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload a LinkedIn CSV file to import contacts."""
    # Rate limit check
    allowed, count = await check_rate_limit(
        current_user.id,
        "csv_upload",
        settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY,
        db,
        is_admin=current_user.is_admin,
    )
    if not allowed:
        raise RateLimitError(
            f"CSV upload limit reached ({settings.RATE_LIMIT_CSV_UPLOADS_PER_DAY}/day)"
        )

    raw_bytes = await _validate_csv_file(file)

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

    # Detect first upload for celebration UX
    prior_uploads = await db.execute(
        select(func.count()).select_from(
            select(CsvUpload.id)
            .where(
                CsvUpload.user_id == current_user.id,
                CsvUpload.id != csv_upload.id,
            )
            .subquery()
        )
    )
    is_first_upload = (prior_uploads.scalar() or 0) == 0

    return {
        "data": CsvUploadResponse.model_validate(csv_upload).model_dump(mode="json"),
        "meta": {"is_first_upload": is_first_upload},
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


@router.post("/nlp-search")
@timed("nlp_search_endpoint")
async def nlp_search(
    body: NlpSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Search contacts using natural language queries."""
    from app.services.nlp_contact_search import search_user_contacts
    from app.utils.tracking import track_action

    query_text = body.query.strip()
    search_result = await search_user_contacts(current_user.id, query_text, db)

    # Build full ContactResponse dicts from the lightweight service results
    # The service returns plain dicts; the endpoint adds the full envelope.
    data = []
    for r in search_result["results"]:
        # Re-query contact for full response? No — service returns what we need.
        # For backward compat, build a dict that matches the old shape.
        data.append(r)

    await track_action(
        db,
        current_user.id,
        "nlp_search",
        metadata_={
            "query": query_text,
            "total_scanned": search_result["total_scanned"],
            "total_matched": search_result["total_matched"],
        },
    )
    await db.commit()

    return {
        "data": data,
        "meta": {
            "interpretation": search_result["interpretation"],
            "total_scanned": search_result["total_scanned"],
            "total_matched": search_result["total_matched"],
        },
    }


# Columns that are encrypted and cannot be sorted/searched at SQL level
_ENCRYPTED_SORT_COLUMNS = {"full_name", "current_company", "connected_on"}


async def _query_contacts_in_memory(
    base_query,
    search: str | None,
    sort_by: str,
    sort_order: str,
    page: int,
    per_page: int,
    db: AsyncSession,
) -> tuple[list, int]:
    """Load, filter, sort, and paginate contacts in-memory (encrypted columns)."""
    result = await db.execute(base_query)
    all_rows = result.all()

    if search:
        s = search.lower()
        all_rows = [
            (c, sc)
            for c, sc in all_rows
            if s in (c.full_name or "").lower()
            or s in (c.current_company or "").lower()
            or s in (c.current_title or "").lower()
            or s in (c.email or "").lower()
        ]

    total = len(all_rows)

    reverse = sort_order == "desc"
    if sort_by == "warm_score":
        all_rows.sort(key=lambda r: (r[1] is not None, r[1] or 0), reverse=reverse)
    elif sort_by == "connected_on":
        from datetime import date as _date

        _min = _date.min
        all_rows.sort(
            key=lambda r: getattr(r[0], "connected_on", None) or _min,
            reverse=reverse,
        )
    elif sort_by == "created_at":
        from datetime import datetime as _dt

        _epoch = _dt.min
        all_rows.sort(
            key=lambda r: getattr(r[0], "created_at", None) or _epoch,
            reverse=reverse,
        )
    else:
        all_rows.sort(
            key=lambda r: (getattr(r[0], sort_by, None) or "").lower(),
            reverse=reverse,
        )

    offset = (page - 1) * per_page
    return all_rows[offset : offset + per_page], total


@router.get("")
@timed("contacts_list")
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
    """List the current user's contacts with pagination, search, and sorting."""
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

    # Non-PII filters can still be applied at SQL level
    if relationship_type:
        base_query = base_query.where(Contact.relationship_type == relationship_type)

    if source:
        base_query = base_query.where(Contact.source == source)

    # Determine whether we need in-memory processing
    need_in_memory = bool(search) or sort_by in _ENCRYPTED_SORT_COLUMNS

    if need_in_memory:
        rows, total = await _query_contacts_in_memory(
            base_query, search, sort_by, sort_order, page, per_page, db
        )
    else:
        # Pure SQL path — no encrypted columns involved in search/sort
        count_query = select(func.count()).select_from(base_query.subquery())
        total = (await db.execute(count_query)).scalar() or 0

        if sort_by == "warm_score":
            sort_col = WarmScore.total_score
            if sort_order == "desc":
                sort_col = sort_col.desc().nullslast()
            else:
                sort_col = sort_col.asc().nullsfirst()
            base_query = base_query.order_by(sort_col)
        else:
            sort_column = getattr(Contact, sort_by)
            if sort_order == "desc":
                sort_column = sort_column.desc()
            base_query = base_query.order_by(sort_column)

        offset = (page - 1) * per_page
        base_query = base_query.offset(offset).limit(per_page)

        result = await db.execute(base_query)
        rows = result.all()

    data = []
    for contact, sco[RESEND_KEY_REDACTED] in rows:
        resp = ContactResponse.model_validate(contact).model_dump(mode="json")
        resp["warm_score"] = float(sco[RESEND_KEY_REDACTED]) if sco[RESEND_KEY_REDACTED] is not None else None
        data.append(resp)

    # Track funnel step
    from app.utils.tracking import track_action

    await track_action(
        db,
        current_user.id,
        "contacts_list",
        metadata_={"page": page, "total": total},
    )

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
    """Retrieve a single contact by ID with its warm score."""
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
    """Soft-delete a contact."""
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

    # Compute blind indexes for suppression/dedup lookups
    email_bi = compute_blind_index(data.email) if data.email else None
    name_co_bi = None
    if data.first_name and data.last_name and data.company:
        name_co_bi = compute_blind_index(
            f"{data.first_name.strip()}{data.last_name.strip()}{data.company.strip()}"
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
        email_blind_index=email_bi,
        name_company_blind_index=name_co_bi,
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
