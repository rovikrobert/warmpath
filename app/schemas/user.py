import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class IntentUpdate(BaseModel):
    intent: str = Field(..., max_length=20)
    full_name: str | None = Field(None, max_length=200)


class DeleteAccountRequest(BaseModel):
    confirm_deletion: bool


class UserCapabilities(BaseModel):
    has_contacts: bool
    has_searches: bool
    has_listings: bool
    has_subscription: bool
    facilitation_count: int


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    plan_tier: str
    intent: str | None = None
    email_verified: bool
    onboarding_complete: bool = False
    created_at: datetime
    capabilities: UserCapabilities | None = None

    model_config = {"from_attributes": True}


class WorkHistoryEntry(BaseModel):
    company: str = Field(..., max_length=255)
    title: str | None = Field(default=None, max_length=255)
    start_date: str | None = Field(default=None, max_length=30)
    end_date: str | None = Field(default=None, max_length=30)


class ConnectorProfileUpsert(BaseModel):
    headline: str | None = Field(default=None, max_length=500)
    current_company: str | None = Field(default=None, max_length=255)
    current_title: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=255)
    linkedin_url: str | None = Field(default=None, max_length=500)
    github_url: str | None = Field(default=None, max_length=500)
    portfolio_url: str | None = Field(default=None, max_length=500)
    personal_site_url: str | None = Field(default=None, max_length=500)
    bio_summary: str | None = Field(default=None, max_length=2000)
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
    github_url: str | None = None
    portfolio_url: str | None = None
    personal_site_url: str | None = None
    bio_summary: str | None
    work_history: list | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
    target_companies: list[str] | None = None
    open_to_remote: bool = True
    career_level: str | None = Field(default=None, max_length=50)
    years_experience: int | None = Field(default=None, ge=0, le=50)
    key_skills: list[str] | None = None
    salary_min: int | None = None
    salary_max: int | None = None


class JobPreferencesResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    target_role: str | None = None
    target_seniority: str | None = None
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    target_companies: list[str] | None = None
    open_to_remote: bool = True
    career_level: str | None = None
    years_experience: int | None = None
    key_skills: list[str] | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    job_search_status: str = "active"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
