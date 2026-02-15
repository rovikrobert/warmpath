import uuid
from datetime import datetime

from pydantic import BaseModel


class MatchResultResponse(BaseModel):
    id: uuid.UUID
    search_request_id: uuid.UUID
    contact_id: uuid.UUID
    warm_score: float
    explanation: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WarmScoreResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    contact_id: uuid.UUID
    total_score: float
    recency_score: float
    context_score: float
    role_score: float
    tenu[RESEND_KEY_REDACTED]: float
    sco[RESEND_KEY_REDACTED]: dict | None = None
    algorithm_version: str
    computed_at: datetime

    model_config = {"from_attributes": True}
