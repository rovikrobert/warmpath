import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    # Optional connector profile fields (created during signup if any provided)
    headline: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    industry: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    bio_summary: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    plan_tier: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ConnectorProfileUpsert(BaseModel):
    headline: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    industry: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    bio_summary: str | None = None


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
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
