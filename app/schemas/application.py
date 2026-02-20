import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# Valid application statuses
VALID_STATUSES = {
    "draft",
    "message_sent",
    "responded",
    "interview_scheduled",
    "interviewed",
    "offer_received",
    "offer_accepted",
    "rejected",
    "withdrawn",
    "no_response",
}


class ApplicationCreate(BaseModel):
    company_name: str = Field(..., max_length=500)
    role_title: str | None = Field(default=None, max_length=500)
    contact_id: uuid.UUID | None = None
    job_opening_id: uuid.UUID | None = None
    match_result_id: uuid.UUID | None = None
    channel: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)


class ApplicationUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=50)
    notes: str | None = Field(default=None, max_length=2000)
    follow_up_at: datetime | None = None
    responded_at: datetime | None = None


class ApplicationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    company_name: str
    role_title: str | None = None
    status: str
    channel: str | None = None
    contact_id: uuid.UUID | None = None
    job_opening_id: uuid.UUID | None = None
    match_result_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    notes: str | None = None
    sent_at: datetime | None = None
    responded_at: datetime | None = None
    follow_up_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Outcome attribution
    source_type: str | None = None
    source_listing_id: uuid.UUID | None = None
    source_intro_id: uuid.UUID | None = None
    outcome: str | None = None
    outcome_at: datetime | None = None

    # Enriched fields (populated from joins)
    contact_name: str | None = None
    company_info: dict | None = None
    job_opening_title: str | None = None
    days_since_sent: int | None = None
    needs_follow_up: bool = False

    model_config = {"from_attributes": True}


class ApplicationStatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    response_rate: float
    interview_rate: float
    avg_days_to_response: float | None
    best_channel: str | None
