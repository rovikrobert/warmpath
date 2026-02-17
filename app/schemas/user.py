import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)
    full_name: str = Field(..., max_length=200)
    # Optional connector profile fields (created during signup if any provided)
    headline: str | None = Field(default=None, max_length=500)
    current_company: str | None = Field(default=None, max_length=500)
    current_title: str | None = Field(default=None, max_length=500)
    industry: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    linkedin_url: str | None = Field(default=None, max_length=500)
    bio_summary: str | None = Field(default=None, max_length=2000)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)


class UserTypeUpdate(BaseModel):
    user_type: str = Field(..., max_length=50)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., max_length=500)
    new_password: str = Field(..., max_length=128)


class DeleteAccountRequest(BaseModel):
    password: str = Field(..., max_length=128)
    confirm_deletion: bool


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    plan_tier: str
    user_type: str
    email_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str = Field(..., max_length=2000)
    token_type: str = "bearer"


class WorkHistoryEntry(BaseModel):
    company: str = Field(..., max_length=255)
    title: str | None = Field(default=None, max_length=255)
    start_date: str | None = Field(default=None, max_length=30)
    end_date: str | None = Field(default=None, max_length=30)


class ConnectorProfileUpsert(BaseModel):
    headline: str | None = Field(default=None, max_length=500)
    current_company: str | None = None
    current_title: str | None = None
    industry: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    bio_summary: str | None = None
    work_history: list[WorkHistoryEntry] | None = None


class ConnectorProfileResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    headline: str | None
    current_company: str | None
    current_title: str | None
    industry: str | None
    location: str | None
    linkedin_url: str | None
    bio_summary: str | None
    work_history: list | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# -- Job Preferences --


class LinkedInCallbackRequest(BaseModel):
    code: str = Field(..., max_length=500)
    state: str = Field(..., max_length=500)
    full_name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    password: str | None = Field(default=None, max_length=128)


class ResumeParseResponse(BaseModel):
    headline: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    industry: str | None = None
    location: str | None = None
    bio_summary: str | None = None
    work_history: list[WorkHistoryEntry] | None = None


class JobPreferencesCreate(BaseModel):
    target_role: str = Field(..., max_length=200)
    target_seniority: str | None = Field(default=None, max_length=100)
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    open_to_remote: bool = True
    salary_min: int | None = None
    salary_max: int | None = None


class JobPreferencesResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    target_role: str | None = None
    target_seniority: str | None = None
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    open_to_remote: bool = True
    salary_min: int | None = None
    salary_max: int | None = None
    job_search_status: str = "active"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
