import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.utils.performance import timed

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Cookie,
    Depends,
    HTTPException,
    Query,
    Response,
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
    ChangePasswordRequest,
    ConnectorProfileResponse,
    ConnectorProfileUpsert,
    DeleteAccountRequest,
    ForgotPasswordRequest,
    IntentUpdate,
    LinkedInCallbackRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserTypeUpdate,
)
from app.services.audit_logger import log_event
from app.services.credits import earn_credits
from app.services.data_retention import archive_credit_history
from app.services.email_service import (
    _send_email,
    send_password_reset_email,
    send_verification_email,
    verify_token,
)
from app.services.linkedin_oauth import (
    exchange_code,
    fetch_profile,
    get_authorize_url,
)
from app.services.resume_parser import ResumeParseError, parse_resume
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    validate_password_strength,
    verify_password,
)

logger = logging.getLogger(__name__)

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
@timed("auth_signup")
async def signup(
    body: UserCreate,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Register a new user account and return access tokens."""
    try:
        validate_password_strength(body.password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

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

    # Check if this email was previously deleted — skip welcome bonus if so
    email_hash = hashlib.sha256(body.email.lower().strip().encode()).hexdigest()
    suppression_result = await db.execute(
        select(SuppressionList).where(
            SuppressionList.email_hash == email_hash,
            SuppressionList.reason == "account_deleted",
        )
    )
    if suppression_result.scalars().first() is None:
        await earn_credits(user.id, 50, "welcome_bonus", db)

    # Send verification email
    await send_verification_email(user, db)

    # Send welcome email (intent set later during onboarding, not at signup)
    from app.services.email_engagement import send_welcome_email_js

    await send_welcome_email_js(user, db)

    # Track funnel step
    from app.models.enrichment import UsageLog

    db.add(UsageLog(user_id=user.id, action="signup"))

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
@timed("auth_login")
async def login(
    body: UserLogin,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Authenticate a user and return access tokens."""
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

    if user is None:
        await log_event(db, "login_failure", metadata={"email": body.email})
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if user.password_hash is None or not verify_password(
        body.password, user.password_hash
    ):
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

    # Pre-warm job cache in background so Find Referrals loads instantly
    from app.services.job_recommendations import warm_job_cache_for_user

    background_tasks.add_task(warm_job_cache_for_user, str(user.id))

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
# Delete account
# ---------------------------------------------------------------------------


@router.post("/delete-account")
async def delete_account(
    body: DeleteAccountRequest,
    response: Response,
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

    # Verify password (OAuth-only users must still confirm via password field check)
    if current_user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please set a password before deleting your account",
        )
    if not verify_password(body.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Password is incorrect",
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
    #    Use SQL DELETE (not ORM session.delete) so the DB-level CASCADE fires
    #    reliably regardless of ORM session state.
    await db.execute(delete(User).where(User.id == user_id))
    await db.commit()

    # 6. Clear refresh cookie
    _clear_refresh_cookie(response)

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
    if current_user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No password set. Use 'Set Password' to create one.",
        )
    if not verify_password(body.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
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
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the authenticated user's profile with capabilities."""
    from app.services.capabilities import compute_user_capabilities

    caps = await compute_user_capabilities(current_user.id, db)
    response = UserResponse.model_validate(current_user).model_dump(mode="json")
    response["capabilities"] = caps.model_dump()
    return {"data": response, "meta": {}}


@router.patch("/user-type")
async def update_user_type(
    body: UserTypeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update the user's role type (job seeker, network holder, or both)."""
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

    # Track funnel step
    from app.models.enrichment import UsageLog

    db.add(UsageLog(user_id=user.id, action="email_verify"))

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


# ---------------------------------------------------------------------------
# LinkedIn OAuth
# ---------------------------------------------------------------------------


@router.get("/linkedin/authorize")
async def linkedin_authorize() -> dict:
    """Generate a LinkedIn OAuth2 authorization URL with a signed state token."""
    if not settings.LINKEDIN_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LinkedIn login is not configured",
        )
    nonce = secrets.token_urlsafe(32)
    # Encode state as a short-lived JWT (10 min) so we can verify it on callback
    from jose import jwt as jose_jwt

    state_payload = {
        "nonce": nonce,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        "type": "linkedin_state",
    }
    state = jose_jwt.encode(state_payload, settings.SECRET_KEY, algorithm="HS256")
    url = get_authorize_url(state)
    return {"data": {"url": url, "state": state}, "meta": {}}


@router.post("/linkedin/callback")
async def linkedin_callback(
    body: LinkedInCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Handle LinkedIn OAuth callback — login existing user or create new one."""
    if not settings.LINKEDIN_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="LinkedIn login is not configured",
        )
    # 1. Verify state token
    from jose import JWTError as JoseJWTError
    from jose import jwt as jose_jwt

    try:
        state_data = jose_jwt.decode(
            body.state, settings.SECRET_KEY, algorithms=["HS256"]
        )
    except JoseJWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired state token",
        )
    if state_data.get("type") != "linkedin_state":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state token",
        )

    # 2. Exchange code for access token + fetch profile
    try:
        access_token = await exchange_code(body.code)
        li_profile = await fetch_profile(access_token)
    except Exception:
        logger.exception("LinkedIn OAuth exchange failed")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with LinkedIn",
        )

    li_sub = li_profile["sub"]
    li_email = li_profile.get("email", "").lower().strip()
    li_name = li_profile.get("name", "")

    # Use frontend-provided values if available, LinkedIn data as fallback
    account_email = body.email.lower().strip() if body.email else li_email
    account_name = body.full_name or li_name
    account_password_hash = None
    if body.password:
        try:
            validate_password_strength(body.password)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(e),
            )
        account_password_hash = hash_password(body.password)

    # 3. Check if user with this LinkedIn identity already exists
    result = await db.execute(
        select(User).where(
            User.oauth_provider == "linkedin",
            User.oauth_provider_id == li_sub,
            User.deleted_at.is_(None),
        )
    )
    existing_oauth_user = result.scalar_one_or_none()

    is_new_user = False

    if existing_oauth_user is not None:
        # Existing LinkedIn user — login
        user = existing_oauth_user
    else:
        # Check if email matches an existing account
        lookup_email = account_email or li_email
        if lookup_email:
            result = await db.execute(
                select(User).where(
                    User.email == lookup_email, User.deleted_at.is_(None)
                )
            )
            existing_email_user = result.scalar_one_or_none()
        else:
            existing_email_user = None

        if existing_email_user is not None:
            # Link LinkedIn identity to existing email/password account
            existing_email_user.oauth_provider = "linkedin"
            existing_email_user.oauth_provider_id = li_sub
            user = existing_email_user
        else:
            # Create new user — with password if frontend provided one
            user = User(
                email=account_email,
                password_hash=account_password_hash,
                full_name=account_name,
                email_verified=not account_password_hash,  # Only auto-verify if no password (pure OAuth)
                oauth_provider="linkedin",
                oauth_provider_id=li_sub,
            )
            db.add(user)
            await db.flush()

            # If user provided password, send verification email (they entered their own email)
            if account_password_hash:
                await send_verification_email(user, db)

            # Check suppression list before welcome bonus
            email_hash = hashlib.sha256(account_email.encode()).hexdigest()
            suppression_result = await db.execute(
                select(SuppressionList).where(
                    SuppressionList.email_hash == email_hash,
                    SuppressionList.reason == "account_deleted",
                )
            )
            if suppression_result.scalars().first() is None:
                await earn_credits(user.id, 50, "welcome_bonus", db)

            is_new_user = True

    # Reset lockout on successful OAuth login
    user.failed_login_attempts = 0
    user.locked_until = None

    access_token_jwt = create_access_token(user.id, user.token_version)
    refresh_token_jwt = create_refresh_token(user.id, user.token_version)
    _set_refresh_cookie(response, refresh_token_jwt)

    await log_event(
        db,
        "login_linkedin" if not is_new_user else "signup_linkedin",
        user_id=user.id,
    )
    await db.commit()

    return {
        "data": {
            "access_token": access_token_jwt,
            "token_type": "bearer",
            "is_new_user": is_new_user,
            "profile": {
                "name": li_name,
                "email": li_email,
                "given_name": li_profile.get("given_name", ""),
                "family_name": li_profile.get("family_name", ""),
                "picture": li_profile.get("picture"),
            },
        },
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
        )

    # Log usage
    from app.models.enrichment import UsageLog

    usage_entry = UsageLog(
        user_id=current_user.id,
        action="resume_parse",
        metadata_={"filename": file.filename},
    )
    db.add(usage_entry)
    await db.commit()

    return {"data": parsed, "meta": {}}


# ---------------------------------------------------------------------------
# Forgot / Reset password
# ---------------------------------------------------------------------------


@router.post("/forgot-password")
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Send a password reset email. Always returns success (no email enumeration)."""
    result = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if user is not None:
        # Skip sending for OAuth-only users (no password to reset),
        # but return the same generic message to prevent enumeration.
        if not (user.password_hash is None and user.oauth_provider):
            # Rate limit: 1 per 5 minutes — silently skip to avoid
            # leaking account existence via a 429 response.
            rate_limited = False
            if user.password_reset_sent_at is not None:
                sent_at = user.password_reset_sent_at
                if sent_at.tzinfo is None:
                    sent_at = sent_at.replace(tzinfo=timezone.utc)
                elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
                if elapsed < 300:
                    rate_limited = True

            if not rate_limited:
                await send_password_reset_email(user, db)
                await db.commit()

    # Always return the same message regardless of whether the email exists,
    # the user is rate-limited, or the account is OAuth-only.
    return {
        "data": {"message": "If that email is registered, a reset link has been sent"},
        "meta": {},
    }


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Reset password using a valid reset token."""
    result = await db.execute(
        select(User).where(
            User.password_reset_token == body.token,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    # Check token is less than 1 hour old
    if user.password_reset_sent_at is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    sent_at = user.password_reset_sent_at
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - sent_at).total_seconds()
    if elapsed > 3600:  # 1 hour
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reset token has expired",
        )

    # Validate password strength
    try:
        validate_password_strength(body.new_password)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e),
        )

    # Update password and invalidate all sessions
    user.password_hash = hash_password(body.new_password)
    user.token_version += 1
    user.password_reset_token = None
    user.password_reset_sent_at = None

    await log_event(db, "password_reset", user_id=user.id)
    await db.commit()

    return {"data": {"message": "Password has been reset successfully"}, "meta": {}}
