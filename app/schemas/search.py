import json
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class SearchRequestCreate(BaseModel):
    name: str
    description: str | None = None
    target_titles: list[str] | None = None
    target_companies: list[str] | None = None
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    target_keywords: list[str] | None = None


class SearchRequestResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    target_titles: list[str] | None = None
    target_companies: list[str] | None = None
    target_industries: list[str] | None = None
    target_locations: list[str] | None = None
    target_keywords: list[str] | None = None
    status: str
    last_run_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator(
        "target_titles",
        "target_companies",
        "target_industries",
        "target_locations",
        "target_keywords",
        mode="before",
    )
    @classmethod
    def _parse_json_arrays(cls, v: object) -> object:
        if isinstance(v, str):
            return json.loads(v)
        return v


class MatchResultResponse(BaseModel):
    id: uuid.UUID
    search_request_id: uuid.UUID
    contact_id: uuid.UUID
    relevance_score: float
    match_reasoning: str
    match_type: str
    warm_score: float | None = None
    combined_score: float | None = None
    # Inline contact info for convenience
    contact_name: str | None = None
    contact_title: str | None = None
    contact_company: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
