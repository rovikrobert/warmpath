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
