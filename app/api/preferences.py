from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.job import UserJobPreferences
from app.models.user import User
from app.schemas.user import JobPreferencesCreate, JobPreferencesResponse
from app.utils.security import get_current_user

router = APIRouter()


@router.put("/job")
async def upsert_job_preferences(
    body: JobPreferencesCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update job preferences (one per user)."""
    result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()

    if prefs is None:
        prefs = UserJobPreferences(
            user_id=current_user.id,
            target_role=body.target_role,
            target_seniority=body.target_seniority,
            target_industries=body.target_industries,
            target_locations=body.target_locations,
            target_companies=body.target_companies,
            open_to_remote=body.open_to_remote,
            career_level=body.career_level,
            years_experience=body.years_experience,
            key_skills=body.key_skills,
            salary_min=body.salary_min,
            salary_max=body.salary_max,
        )
        db.add(prefs)
    else:
        prefs.target_role = body.target_role
        prefs.target_seniority = body.target_seniority
        prefs.target_industries = body.target_industries
        prefs.target_locations = body.target_locations
        prefs.target_companies = body.target_companies
        prefs.open_to_remote = body.open_to_remote
        prefs.career_level = body.career_level
        prefs.years_experience = body.years_experience
        prefs.key_skills = body.key_skills
        prefs.salary_min = body.salary_min
        prefs.salary_max = body.salary_max

    await db.commit()
    await db.refresh(prefs)

    return {
        "data": JobPreferencesResponse.model_validate(prefs).model_dump(mode="json"),
        "meta": {},
    }


@router.get("/job")
async def get_job_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve the current user's job preferences."""
    result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job preferences not set",
        )

    return {
        "data": JobPreferencesResponse.model_validate(prefs).model_dump(mode="json"),
        "meta": {},
    }


@router.delete("/job")
async def delete_job_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete the current user's job preferences."""
    result = await db.execute(
        select(UserJobPreferences).where(UserJobPreferences.user_id == current_user.id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job preferences not set",
        )

    await db.delete(prefs)
    await db.commit()

    return {"data": {"deleted": True}, "meta": {}}
