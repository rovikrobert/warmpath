import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FriendRequestCreate(BaseModel):
    addressee_id: uuid.UUID


class FriendRequestAction(BaseModel):
    action: str = Field(..., pattern="^(accept|decline)$")


class FriendRequestResponse(BaseModel):
    id: uuid.UUID
    requester_id: uuid.UUID
    addressee_id: uuid.UUID
    status: str
    requested_at: datetime
    responded_at: datetime | None = None
    requester_name: str | None = None
    requester_headline: str | None = None
    requester_company: str | None = None
    addressee_name: str | None = None
    addressee_headline: str | None = None

    model_config = {"from_attributes": True}


class FriendSummary(BaseModel):
    friend_id: uuid.UUID
    full_name: str
    headline: str | None = None
    current_company: str | None = None
    current_title: str | None = None
    friend_since: datetime

    model_config = {"from_attributes": True}


class BlockUserRequest(BaseModel):
    user_id: uuid.UUID


class BlockedUserResponse(BaseModel):
    blocked_id: uuid.UUID
    full_name: str
    created_at: datetime

    model_config = {"from_attributes": True}
