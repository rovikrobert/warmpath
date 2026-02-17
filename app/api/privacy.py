"""Privacy API — GDPR/CCPA/PDPA compliance endpoints.

Endpoints:
  GET    /privacy/export-data           — download all personal data (DSAR)
  POST   /privacy/restrict-processing   — restrict data processing
  POST   /privacy/unrestrict-processing — remove processing restriction
  POST   /privacy/marketing-opt-out     — opt out of marketing
  POST   /privacy/marketing-opt-in      — opt back into marketing
  POST   /privacy/consent               — record/withdraw consent for an activity
  GET    /privacy/consent               — list consent records
  POST   /privacy/suppression-request   — public: request removal from all vaults
  POST   /privacy/data-request          — submit a formal DSAR
  POST   /privacy/rectification         — request data correction across vaults
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.privacy import ConsentRecord
from app.models.user import User
from app.services.audit_logger import log_event
from app.services.breach_notification import create_data_request
from app.services.data_export import export_user_data
from app.services.suppression import add_to_suppression, rectify_contact_data
from app.utils.security import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SuppressionRequestBody(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None


class ConsentBody(BaseModel):
    activity: str = Field(..., min_length=1, max_length=50)
    action: str = Field(..., pattern="^(granted|withdrawn)$")


class DataRequestBody(BaseModel):
    request_type: str = Field(
        ..., pattern="^(access|deletion|rectification|restriction|portability|objection)$"
    )
    details: str | None = None
    regulation: str = Field(default="general", pattern="^(gdpr|ccpa|pdpa|general)$")


class RectificationBody(BaseModel):
    email: EmailStr | None = None
    first_name: str | None = None
    last_name: str | None = None
    company: str | None = None
    corrections: dict = Field(..., min_length=1)


# ---------------------------------------------------------------------------
# Data export (Gap 2)
# ---------------------------------------------------------------------------


@router.get("/export-data")
async def export_data(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Export all personal data for the authenticated user (DSAR compliance)."""
    data = await export_user_data(current_user.id, db)
    await log_event(db, "data_export", user_id=current_user.id)
    await db.commit()
    return {"data": data, "meta": {}}


# ---------------------------------------------------------------------------
# Restrict / unrestrict processing (Gap 4)
# ---------------------------------------------------------------------------


@router.post("/restrict-processing")
async def restrict_processing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Restrict processing of the user's data (GDPR Article 18)."""
    current_user.processing_restricted = True
    await log_event(
        db, "processing_restricted", user_id=current_user.id,
    )
    await db.commit()
    return {"data": {"message": "Data processing has been restricted"}, "meta": {}}


@router.post("/unrestrict-processing")
async def unrestrict_processing(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove processing restriction on the user's data."""
    current_user.processing_restricted = False
    await log_event(
        db, "processing_unrestricted", user_id=current_user.id,
    )
    await db.commit()
    return {"data": {"message": "Data processing restriction removed"}, "meta": {}}


# ---------------------------------------------------------------------------
# Marketing opt-out / opt-in (Gap 5)
# ---------------------------------------------------------------------------


@router.post("/marketing-opt-out")
async def marketing_opt_out(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Opt out of marketing communications (GDPR right to object)."""
    current_user.marketing_opt_out = True
    await log_event(db, "marketing_opt_out", user_id=current_user.id)
    await db.commit()
    return {"data": {"message": "Opted out of marketing communications"}, "meta": {}}


@router.post("/marketing-opt-in")
async def marketing_opt_in(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Opt back into marketing communications."""
    current_user.marketing_opt_out = False
    await log_event(db, "marketing_opt_in", user_id=current_user.id)
    await db.commit()
    return {"data": {"message": "Opted into marketing communications"}, "meta": {}}


# ---------------------------------------------------------------------------
# Consent tracking (Gap 6)
# ---------------------------------------------------------------------------


@router.post("/consent")
async def record_consent(
    body: ConsentBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Record or withdraw consent for a specific processing activity."""
    record = ConsentRecord(
        user_id=current_user.id,
        activity=body.activity,
        consented=body.action,
    )
    db.add(record)
    await log_event(
        db,
        f"consent_{body.action}",
        user_id=current_user.id,
        metadata={"activity": body.activity},
    )
    await db.commit()
    return {
        "data": {
            "activity": body.activity,
            "action": body.action,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        },
        "meta": {},
    }


@router.get("/consent")
async def list_consent(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List all consent records for the current user."""
    result = await db.execute(
        select(ConsentRecord)
        .where(ConsentRecord.user_id == current_user.id)
        .order_by(ConsentRecord.created_at.desc())
    )
    records = [
        {
            "activity": r.activity,
            "action": r.consented,
            "recorded_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in result.scalars()
    ]
    return {"data": records, "meta": {"total": len(records)}}


# ---------------------------------------------------------------------------
# Public suppression request (Gap 10)
# ---------------------------------------------------------------------------


@router.post("/suppression-request")
async def suppression_request(
    body: SuppressionRequestBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: request removal of personal data from all vaults.

    Does not require authentication (non-users need to submit removal requests).
    Requires at least email or (first_name + last_name + company).
    """
    if not body.email and not (body.first_name and body.last_name and body.company):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide email and/or full name + company for identification",
        )

    await add_to_suppression(
        email=body.email,
        first_name=body.first_name or "",
        last_name=body.last_name or "",
        company=body.company or "",
        reason="self_request",
        db=db,
    )
    await db.commit()

    return {
        "data": {
            "message": (
                "Your removal request has been processed. "
                "Matching records will be purged from all vaults."
            )
        },
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Data rectification (Gap 3)
# ---------------------------------------------------------------------------


@router.post("/rectification")
async def request_rectification(
    body: RectificationBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Public endpoint: request correction of personal data across all vaults.

    Requires identification (email or name+company) plus corrections dict.
    """
    if not body.email and not (body.first_name and body.last_name and body.company):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide email and/or full name + company for identification",
        )

    count = await rectify_contact_data(
        email=body.email,
        first_name=body.first_name,
        last_name=body.last_name,
        company=body.company,
        corrections=body.corrections,
        db=db,
    )
    await db.commit()

    return {
        "data": {
            "message": f"Corrections applied to {count} matching record(s)",
            "records_updated": count,
        },
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Formal DSAR submission (Gap 9)
# ---------------------------------------------------------------------------


@router.post("/data-request")
async def submit_data_request(
    body: DataRequestBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit a formal data subject access request (DSAR) with tracked deadline."""
    request = await create_data_request(
        request_type=body.request_type,
        requester_email=current_user.email,
        user_id=current_user.id,
        details={"notes": body.details} if body.details else None,
        regulation=body.regulation,
        db=db,
    )
    await db.commit()

    return {
        "data": {
            "request_id": str(request.id),
            "request_type": body.request_type,
            "status": "pending",
            "deadline": request.deadline_at.isoformat(),
            "message": (
                "Your request has been received and will be processed "
                f"within the regulatory deadline ({request.deadline_at.strftime('%Y-%m-%d')})."
            ),
        },
        "meta": {},
    }
