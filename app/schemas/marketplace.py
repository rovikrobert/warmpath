import uuid
from datetime import datetime

from pydantic import BaseModel


class MarketplaceListingResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    role_level: str
    department_category: str
    warm_sco[RESEND_KEY_REDACTED]: str
    connection_recency: str
    is_available: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NetworkSharingPreferencesCreate(BaseModel):
    opt_in_marketplace: bool = False
    category_filters: dict | None = None
    excluded_contact_ids: list[str] | None = None
    is_paused: bool = False


class NetworkSharingPreferencesResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    opt_in_marketplace: bool
    category_filters: dict | None = None
    excluded_contact_ids: list[str] | None = None
    is_paused: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class IntroFacilitationCreate(BaseModel):
    marketplace_listing_id: uuid.UUID
    job_seeker_profile_snapshot: dict | None = None


class IntroFacilitationResponse(BaseModel):
    id: uuid.UUID
    job_seeker_id: uuid.UUID
    network_holder_id: uuid.UUID
    marketplace_listing_id: uuid.UUID
    status: str
    job_seeker_profile_snapshot: dict | None = None
    network_holder_notes: str | None = None
    requested_at: datetime
    reviewed_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
