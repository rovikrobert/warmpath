import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.contact import Contact, CsvUpload
from app.models.match_result import WarmScore
from app.models.user import User
from app.schemas.contact import ContactResponse, CsvUploadResponse, PaginationMeta
from app.services.company_normalizer import link_contact_to_company
from app.services.csv_parser import parse_linkedin_csv
from app.services.warm_scorer import batch_compute_scores
from app.utils.security import get_current_user

router = APIRouter()


def _contact_to_response(contact: Contact, warm_score_val: float | None = None) -> dict:
    resp = ContactResponse.model_validate(contact).model_dump(mode="json")
    if warm_score_val is not None:
        resp["warm_score"] = warm_score_val
    return resp


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_csv(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted",
        )

    raw_bytes = await file.read()

    # Create csv_upload record
    csv_upload = CsvUpload(
        user_id=current_user.id,
        filename=file.filename,
        file_size_bytes=len(raw_bytes),
        status="processing",
        started_at=datetime.now(timezone.utc),
    )
    db.add(csv_upload)
    await db.flush()

    # Parse CSV
    try:
        parsed = parse_linkedin_csv(raw_bytes)
    except Exception as exc:
        csv_upload.status = "failed"
        csv_upload.error_message = str(exc)
        csv_upload.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse CSV: {exc}",
        ) from exc

    csv_upload.row_count = len(parsed)

    # Upsert contacts — deduplicate by fingerprint within this user's contacts
    processed = 0
    errors = 0
    for row in parsed:
        fingerprint = row.get("fingerprint")
        if fingerprint:
            result = await db.execute(
                select(Contact).where(
                    Contact.user_id == current_user.id,
                    Contact.fingerprint == fingerprint,
                    Contact.deleted_at.is_(None),
                )
            )
            existing = result.scalar_one_or_none()
        else:
            existing = None

        if existing:
            # Update existing contact with fresh data
            existing.first_name = row["first_name"]
            existing.last_name = row["last_name"]
            existing.full_name = row["full_name"]
            existing.email = row.get("email") or existing.email
            existing.current_title = row.get("current_title") or existing.current_title
            existing.current_company = (
                row.get("current_company") or existing.current_company
            )
            existing.linkedin_url = row.get("linkedin_url") or existing.linkedin_url
            existing.connected_on = row.get("connected_on") or existing.connected_on
            existing.raw_csv_row = row.get("raw_csv_row")
            existing.csv_upload_id = csv_upload.id
            await link_contact_to_company(existing, db)
            processed += 1
        else:
            contact = Contact(
                user_id=current_user.id,
                csv_upload_id=csv_upload.id,
                first_name=row["first_name"],
                last_name=row["last_name"],
                full_name=row["full_name"],
                email=row.get("email"),
                current_title=row.get("current_title"),
                current_company=row.get("current_company"),
                linkedin_url=row.get("linkedin_url"),
                connected_on=row.get("connected_on"),
                fingerprint=fingerprint,
                raw_csv_row=row.get("raw_csv_row"),
            )
            db.add(contact)
            await db.flush()
            await link_contact_to_company(contact, db)
            processed += 1

    csv_upload.processed_count = processed
    csv_upload.error_count = errors
    csv_upload.status = "completed"
    csv_upload.completed_at = datetime.now(timezone.utc)

    # Auto-compute warm scores after upload
    await batch_compute_scores(current_user.id, db)

    await db.commit()
    await db.refresh(csv_upload)

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
            (WarmScore.contact_id == Contact.id) & (WarmScore.user_id == Contact.user_id),
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
            (WarmScore.contact_id == Contact.id) & (WarmScore.user_id == Contact.user_id),
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
