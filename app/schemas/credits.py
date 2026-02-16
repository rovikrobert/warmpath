import uuid
from datetime import datetime

from pydantic import BaseModel


class CreditTransactionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    amount: int
    type: str
    reason: str
    reference_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
