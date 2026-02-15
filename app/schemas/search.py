import uuid
from datetime import datetime

from pydantic import BaseModel


class SearchRequestCreate(BaseModel):
    title: str
    target_role: str | None = None
    target_company: str | None = None
    target_industry: str | None = None
    description: str | None = None


class SearchRequestResponse(BaseModel):
    id: uuid.UUID
    title: str
    target_role: str | None
    target_company: str | None
    target_industry: str | None
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
