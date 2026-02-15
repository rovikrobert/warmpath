import uuid
from datetime import date, datetime

from pydantic import BaseModel


# -- CSV Upload --


class CsvUploadResponse(BaseModel):
    id: uuid.UUID
    status: str
    filename: str
    row_count: int | None
    processed_count: int | None
    error_count: int | None
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
    warm_score: float | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


class ContactListResponse(BaseModel):
    data: list[ContactResponse]
    meta: PaginationMeta
