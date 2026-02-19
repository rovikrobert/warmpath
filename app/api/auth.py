import hashlib
import logging
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.privacy import SuppressionList
from app.models.user import ConnectorProfile, User
from app.schemas.user import (
    ConnectorProfileResponse,
    ConnectorProfileUpsert,
    DeleteAccountRequest,
    IntentUpdate,
    UserResponse,
)
from app.services.audit_logger import log_event
from app.services.data_retention import archive_credit_history
from app.services.email_service import _send_email
from app.services.resume_parser import ResumeParseError, parse_resume
from app.utils.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Delete account
# ---------------------------------------------------------------------------


@router.post("/delete-account")
async def delete_account(
    body: DeleteAccountRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Permanently delete the authenticated user's account and all data."""
    # Must explicitly confirm deletion
    if not body.confirm_deletion:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="confirm_deletion must be true",
        )

    # Block if user has active paid subscription
    if current_user.plan_tier != "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please cancel your subscription before deleting your account",
        )

    user_email = current_user.email
    user_id = current_user.id

    # 1. Log audit event BEFORE delete (SET NULL preserves the entry)
    await log_event(
        db,
        "account_deleted",
        user_id=user_id,
        metadata={"email": user_email},
    )

    # 2. Add email hash to suppression list (re-registration guard)
    email_hash = hashlib.sha256(user_email.lower().strip().encode()).hexdigest()
    suppression_entry = SuppressionList(
        email_hash=email_hash,
        reason="account_deleted",
        requested_at=datetime.now(timezone.utc),
    )
    db.add(suppression_entry)

    # 3. Archive credit history before deletion (24-month audit retention)
    await archive_credit_history(user_id, db)

    # 4. Commit audit + suppression + archive before deleting user
    await db.flush()

    # 5. Hard-delete user row — CASCADE removes all child records
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()

    # 6. Delete user from Clerk (best-effort)
    if current_user.clerk_user_id and settings.CLERK_SECRET_KEY:
        try:
            import httpx

            async with httpx.AsyncClient() as http:
                await http.delete(
                    f"https://api.clerk.com/v1/users/{current_user.clerk_user_id}",
                    headers={"Authorization": f"Bearer {settings.CLERK_SECRET_KEY}"},
                )
        except Exception:
            logger.exception("Failed to delete user from Clerk")

    # 7. Send deletion confirmation email (best-effort, outside transaction)
    _send_email(
        to=user_email,
        subject="Your WarmPath account has been deleted",
        html=(
            "<p>Your WarmPath account and all associated data have been "
            "permanently deleted.</p>"
            "<p>If you did not request this, please contact us immediately "
            "at rovik@majiq.agency.</p>"
        ),
    )

    return {
        "data": {"message": "Account permanently deleted"},
        "meta": {},
    }


# ---------------------------------------------------------------------------
# User info / profile
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the authenticated user's profile with capabilities."""
    from app.services.capabilities import compute_user_capabilities

    caps = await compute_user_capabilities(current_user.id, db)
    response = UserResponse.model_validate(current_user).model_dump(mode="json")
    response["onboarding_complete"] = current_user.onboarding_completed_at is not None
    response["capabilities"] = caps.model_dump()
    return {"data": response, "meta": {}}


@router.patch("/intent")
async def update_intent(
    body: IntentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update the user's onboarding intent (personalization only)."""
    valid_intents = {"find_referrals", "sha[RESEND_KEY_REDACTED]", "explore"}
    if body.intent not in valid_intents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"intent must be one of: {', '.join(sorted(valid_intents))}",
        )
    current_user.intent = body.intent
    if body.full_name is not None:
        current_user.full_name = body.full_name
    await db.commit()
    await db.refresh(current_user)
    return {
        "data": {"intent": current_user.intent},
        "meta": {},
    }


@router.post("/profile")
async def upsert_profile(
    body: ConnectorProfileUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update the user's connector profile."""
    result = await db.execute(
        select(ConnectorProfile).where(ConnectorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    fields = body.model_dump(exclude_unset=True)
    # Convert work_history Pydantic models to plain dicts for JSONB
    if "work_history" in fields and fields["work_history"] is not None:
        fields["work_history"] = [
            entry if isinstance(entry, dict) else entry
            for entry in fields["work_history"]
        ]

    if profile is None:
        profile = ConnectorProfile(user_id=current_user.id, **fields)
        db.add(profile)
    else:
        for key, value in fields.items():
            setattr(profile, key, value)

    await db.commit()
    await db.refresh(profile)

    return {
        "data": ConnectorProfileResponse.model_validate(profile).model_dump(
            mode="json"
        ),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Resume import
# ---------------------------------------------------------------------------


@router.post("/profile/import-resume")
async def import_resume(
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Parse a resume PDF and return structured profile data for preview."""
    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are accepted",
        )
    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/octet-stream",
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid content type — expected application/pdf",
        )

    pdf_bytes = await file.read()

    try:
        parsed = await parse_resume(pdf_bytes)
    except ResumeParseError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    # Log usage
    from app.utils.tracking import track_action

    await track_action(
        db, current_user.id, "resume_parse", metadata_={"filename": file.filename}
    )
    await db.commit()

    return {"data": parsed, "meta": {}}
