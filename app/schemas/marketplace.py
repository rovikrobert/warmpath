import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Marketplace Search
# ---------------------------------------------------------------------------


class MarketplaceSearchBody(BaseModel):
    company_names: list[str]
    role_levels: list[str] | None = None
    departments: list[str] | None = None
    query: str | None = (
        None  # Free-text semantic search (requires VECTOR_SEARCH_ENABLED)
    )
    friend_filter: str | None = Field(
        default=None,
        pattern="^(all|friends_only|friends_and_fof)$",
        description="Filter by friend connections: all (default), friends_only, friends_and_fof",
    )


class MarketplaceSearchResult(BaseModel):
    listing_id: uuid.UUID
    company_name: str
    role_level: str
    department_category: str
    warm_score_range: str
    connection_recency: str
    network_holder_reputation: dict | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Marketplace Listings (for holder's own view)
# ---------------------------------------------------------------------------


class MarketplaceListingResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    role_level: str
    department_category: str
    warm_score_range: str
    connection_recency: str
    is_available: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MarketplaceListingDetailResponse(BaseModel):
    """Full listing with contact details — only for the network holder."""

    id: uuid.UUID
    company_id: uuid.UUID
    role_level: str
    department_category: str
    warm_score_range: str
    connection_recency: str
    is_available: bool
    created_at: datetime
    contact_name: str | None = None
    contact_title: str | None = None
    contact_email: str | None = None
    contact_company: str | None = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Sharing Preferences
# ---------------------------------------------------------------------------


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


class NetworkSharingPrefsUpdate(BaseModel):
    opt_in_marketplace: bool
    category_filters: dict | None = None
    excluded_contact_ids: list[str] | None = None
    is_paused: bool = False


# ---------------------------------------------------------------------------
# Intro Facilitation
# ---------------------------------------------------------------------------


class IntroFacilitationCreate(BaseModel):
    marketplace_listing_id: uuid.UUID
    job_seeker_profile_snapshot: dict | None = None


class IntroFacilitationRequest(BaseModel):
    marketplace_listing_id: uuid.UUID
    message_to_holder: str | None = Field(default=None, max_length=2000)
    profile_visibility: str = Field(default="summary", max_length=50)
    # Request type and context fields
    request_type: str = Field(default="specific_role", max_length=30)
    job_title: str | None = Field(default=None, max_length=255)
    job_url: str | None = Field(default=None, max_length=2000)
    job_description: str | None = Field(default=None, max_length=5000)
    exploration_context: str | None = Field(default=None, max_length=2000)


class IntroFacilitationActionBody(BaseModel):
    action: str = Field(..., max_length=20)  # "approve" or "decline"
    notes: str | None = Field(default=None, max_length=2000)


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
    listing_summary: MarketplaceSearchResult | None = None
    delivery_method: str | None = None
    delivery_status: str | None = None
    delivered_at: datetime | None = None
    credits_awarded_at: datetime | None = None

    # LinkedIn fallback fields (not persisted — set in response only)
    linkedin_url: str | None = None
    drafted_message: str | None = None

    model_config = {"from_attributes": True}


class IntroFacilitationHolderResponse(IntroFacilitationResponse):
    """Extended response for network holders — includes their contact details."""

    contact_name: str | None = None
    contact_title: str | None = None
    contact_email: str | None = None
    contact_company: str | None = None

    # Relationship context for NH decision-making
    relationship_type: str | None = None
    would_refer: str | None = None
    how_you_know: str | None = None
