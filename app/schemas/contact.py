import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


VALID_RELATIONSHIP_TYPES = {
    "former_colleague",
    "current_colleague",
    "manager",
    "alumni",
    "industry_peer",
    "friend",
    "mentor",
    "recruiter",
    "other",
}


# -- CSV Upload --


class CsvUploadResponse(BaseModel):
    id: uuid.UUID
    status: str
    filename: str
    row_count: int | None
    processed_count: int | None
    error_count: int | None
    contacts_created: int | None = None
    duplicates_skipped: int | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Contact --


class ContactResponse(BaseModel):
    id: uuid.UUID
    full_name: str
    first_name: str | None = None
    last_name: str | None = None
    current_title: str | None = None
    current_company: str | None = None
    email: str | None = None
    linkedin_url: str | None = None
    connected_on: date | None = None
    relationship_type: str | None = None
    source: str = "linkedin_csv"
    how_you_know: str | None = None
    last_interaction_date: date | None = None
    warm_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactUpdate(BaseModel):
    relationship_type: str | None = None
    how_you_know: str | None = None
    notes: str | None = None

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"relationship_type must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
            )
        return v


class ManualContactCreate(BaseModel):
    first_name: str
    last_name: str
    company: str | None = None
    position: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    relationship_type: str | None = None
    how_you_know: str | None = None
    last_interaction_date: date | None = None

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"relationship_type must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
            )
        return v


class ManualContactBulkCreate(BaseModel):
    contacts: list[ManualContactCreate]

    @field_validator("contacts")
    @classmethod
    def validate_bulk_limit(cls, v: list) -> list:
        if len(v) > 50:
            raise ValueError("Bulk import limited to 50 contacts per request")
        if len(v) == 0:
            raise ValueError("At least one contact is required")
        return v


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class ContactListResponse(BaseModel):
    data: list[ContactResponse]
    meta: PaginationMeta
