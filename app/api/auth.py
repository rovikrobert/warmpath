import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import ConnectorProfile, User
from app.schemas.user import (
    ChangePasswordRequest,
    ConnectorProfileResponse,
    ConnectorProfileUpsert,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserTypeUpdate,
)
from app.services.audit_logger import log_event
from app.services.credits import earn_credits
from app.services.email_service import send_verification_email, verify_token
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

REFRESH_COOKIE_NAME = "warmpath_refresh_token"


def _set_refresh_cookie(response: Response, token: str) -> None:
    """Set the refresh token as an HttpOnly cookie."""
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="strict",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth",  # only sent to auth endpoints
    )


def _clear_refresh_cookie(response: Response) -> None:
    """Delete the refresh token cookie."""
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.SECURE_COOKIES,
        samesite="strict",
        path="/api/v1/auth",
    )


# ---------------------------------------------------------------------------
# Signup / Login
# ---------------------------------------------------------------------------


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(
    body: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.flush()

    # Create connector profile if any profile fields were provided
    profile_fields = {
        k: v
        for k, v in body.model_dump(
            include={
                "headline",
                "current_company",
                "current_title",
                "industry",
                "location",
                "linkedin_url",
                "bio_summary",
            }
        ).items()
        if v is not None
    }
    if profile_fields:
        profile = ConnectorProfile(user_id=user.id, **profile_fields)
        db.add(profile)

    # Award welcome bonus credits
    await earn_credits(user.id, 50, "welcome_bonus", db)

    # Send verification email
    await send_verification_email(user, db)

    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token)

    return {
        "data": TokenResponse(access_token=access_token).model_dump(),
        "meta": {},
    }


@router.post("/login")
async def login(
    body: UserLogin,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    # Check account lockout
    if user is not None and user.locked_until is not None:
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        if locked_until > datetime.now(timezone.utc):
            await log_event(
                db,
                "login_lockout",
                user_id=user.id,
                metadata={"email": body.email},
            )
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account temporarily locked. Try again in 15 minutes.",
            )

    if user is None or not verify_password(body.password, user.password_hash):
        # Track failed login
        if user is not None:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
                await log_event(
                    db,
                    "login_lockout",
                    user_id=user.id,
                    metadata={
                        "email": body.email,
                        "attempts": user.failed_login_attempts,
                    },
                )
            else:
                await log_event(
                    db,
                    "login_failure",
                    user_id=user.id,
                    metadata={"email": body.email},
                )
            await db.commit()
        else:
            await log_event(
                db,
                "login_failure",
                metadata={"email": body.email},
            )
            await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Successful login — reset lockout counters
    user.failed_login_attempts = 0
    user.locked_until = None

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token)

    await log_event(db, "login_success", user_id=user.id)
    await db.commit()

    return {
        "data": TokenResponse(access_token=access_token).model_dump(),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@router.post("/refresh")
async def refresh_token(
    response: Response,
    warmpath_refresh_token: str | None = Cookie(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Accept refresh token from HttpOnly cookie, validate, return new tokens."""
    if not warmpath_refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token missing",
        )

    data = decode_token(warmpath_refresh_token, expected_type="refresh")
    user_id = uuid.UUID(data["sub"])
    token_version = data["ver"]

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )
    if token_version != user.token_version:
        # Token version mismatch — possible token reuse/theft
        _clear_refresh_cookie(response)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    # Issue new access + rotated refresh token
    new_access = create_access_token(user.id, user.token_version)
    new_refresh = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, new_refresh)

    await log_event(db, "token_refresh", user_id=user.id)
    await db.commit()

    return {
        "data": TokenResponse(access_token=new_access).model_dump(),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout(response: Response) -> dict:
    """Clear the refresh token cookie (single-session logout)."""
    _clear_refresh_cookie(response)
    return {"data": {"message": "Logged out"}, "meta": {}}


@router.post("/logout-all")
async def logout_all(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Increment token_version to invalidate ALL sessions everywhere."""
    current_user.token_version += 1
    await log_event(db, "logout_all_sessions", user_id=current_user.id)
    await db.commit()
    _clear_refresh_cookie(response)
    return {"data": {"message": "All sessions invalidated"}, "meta": {}}


# ---------------------------------------------------------------------------
# Change password
# ---------------------------------------------------------------------------


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify old password, hash new one, increment token_version."""
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    current_user.password_hash = hash_password(body.new_password)
    current_user.token_version += 1
    await log_event(db, "password_change", user_id=current_user.id)
    await db.commit()

    # Issue fresh tokens with new version
    new_access = create_access_token(current_user.id, current_user.token_version)
    new_refresh = create_refresh_token(current_user.id, current_user.token_version)
    _set_refresh_cookie(response, new_refresh)

    return {
        "data": TokenResponse(access_token=new_access).model_dump(),
        "meta": {},
    }


# ---------------------------------------------------------------------------
# User info / profile
# ---------------------------------------------------------------------------


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "data": UserResponse.model_validate(current_user).model_dump(mode="json"),
        "meta": {},
    }


@router.patch("/user-type")
async def update_user_type(
    body: UserTypeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    valid_types = {"job_seeker", "network_holder", "both"}
    if body.user_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"user_type must be one of: {', '.join(sorted(valid_types))}",
        )
    current_user.user_type = body.user_type
    await db.commit()
    await db.refresh(current_user)
    return {
        "data": {"user_type": current_user.user_type},
        "meta": {},
    }


@router.post("/profile")
async def upsert_profile(
    body: ConnectorProfileUpsert,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
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
# Email verification
# ---------------------------------------------------------------------------


@router.get("/verify-email")
async def verify_email(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Verify a user's email address using the token from the verification email."""
    try:
        user = await verify_token(token, db)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    await log_event(db, "email_verified", user_id=user.id)
    await db.commit()
    return {"data": {"message": "Email verified successfully"}, "meta": {}}


@router.post("/resend-verification")
async def resend_verification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Resend the verification email. Rate limited: 1 per 5 minutes."""
    if current_user.email_verified:
        return {"data": {"message": "Email already verified"}, "meta": {}}

    # Rate limit: 1 per 5 minutes
    if current_user.email_verification_sent_at is not None:
        sent_at = current_user.email_verification_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
        if elapsed < 300:  # 5 minutes
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Please wait 5 minutes before requesting another verification email",
            )

    await send_verification_email(current_user, db)
    await db.commit()
    return {"data": {"message": "Verification email sent"}, "meta": {}}
