from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import ConnectorProfile, User
from app.schemas.user import (
    ConnectorProfileResponse,
    ConnectorProfileUpsert,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserTypeUpdate,
)
from app.services.credits import earn_credits
from app.utils.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter()


@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: UserCreate, db: AsyncSession = Depends(get_db)) -> dict:
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

    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return {
        "data": TokenResponse(access_token=token).model_dump(),
        "meta": {},
    }


@router.post("/login")
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)) -> dict:
    result = await db.execute(
        select(User).where(User.email == body.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    token = create_access_token(user.id)
    return {
        "data": TokenResponse(access_token=token).model_dump(),
        "meta": {},
    }


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
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
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
