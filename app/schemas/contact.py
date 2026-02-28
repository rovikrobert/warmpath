import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


VALID_RELATIONSHIP_TYPES = {
    "former_colleague",
    "current_colleague",
    "manager",
    "alumni",
    "industry_peer",
    "friend",
    "mentor",
    "recruiter",
    "client",
    "vendor",
    "investor",
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
    total_chunks: int | None = None
    chunks_cleaned: int | None = None
    chunks_imported: int | None = None
    completed_at: datetime | None = None
    progress_phase: str | None = None
    error_message: str | None = None
    batch_job_name: str | None = None
    estimated_seconds_remaining: float | None = None
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
    relationship_type: str | None = Field(default=None, max_length=50)
    how_you_know: str | None = Field(default=None, max_length=1000)
    notes: str | None = Field(default=None, max_length=2000)
    warm_score_override: float | None = Field(default=None, ge=0, le=100)

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"relationship_type must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
            )
        return v


class ManualContactCreate(BaseModel):
    first_name: str = Field(..., max_length=200)
    last_name: str = Field(..., max_length=200)
    company: str | None = Field(default=None, max_length=500)
    position: str | None = Field(default=None, max_length=500)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=200)
    relationship_type: str | None = Field(default=None, max_length=50)
    how_you_know: str | None = Field(default=None, max_length=1000)
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


class BulkContactFilter(BaseModel):
    search: str | None = Field(default=None, max_length=500)
    relationship_type: str | None = Field(default=None, max_length=50)
    source: str | None = Field(default=None, max_length=50)


class BulkContactUpdate(BaseModel):
    relationship_type: str = Field(..., max_length=50)
    contact_ids: list[uuid.UUID] | None = None
    filter: BulkContactFilter | None = None

    @field_validator("relationship_type")
    @classmethod
    def validate_relationship_type(cls, v: str) -> str:
        if v not in VALID_RELATIONSHIP_TYPES:
            raise ValueError(
                f"relationship_type must be one of: {', '.join(sorted(VALID_RELATIONSHIP_TYPES))}"
            )
        return v

    def model_post_init(self, __context) -> None:
        has_ids = self.contact_ids is not None and len(self.contact_ids) > 0
        has_filter = self.filter is not None
        if has_ids == has_filter:
            raise ValueError(
                "Provide either contact_ids or filter, not both (and not neither)"
            )
        if has_ids and len(self.contact_ids) > 5000:
            raise ValueError("Bulk update limited to 5000 contacts per request")


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class ContactListResponse(BaseModel):
    data: list[ContactResponse]
    meta: PaginationMeta


# -- NLP Search --


class NlpSearchRequest(BaseModel):
    query: str = Field(..., max_length=500, description="Natural language search query")


class NlpInterpretation(BaseModel):
    titles: list[str] = []
    companies: list[str] = []
    seniority: list[str] = []
    locations: list[str] = []
    relationship_types: list[str] = []
    raw_query: str = ""
