import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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


class CreditBalanceResponse(BaseModel):
    balance: int
    earned_total: int
    spent_total: int
    expiring_soon: int


class CreditHistoryEntry(BaseModel):
    id: uuid.UUID
    amount: int
    type: str
    reason: str
    created_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class CreditPurchaseRequest(BaseModel):
    amount: int = Field(gt=0, le=1000)
