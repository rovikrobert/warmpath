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
    referral_likelihood: str | None = None
    sco[RESEND_KEY_REDACTED]: dict | None = None
    algorithm_version: str
    computed_at: datetime

    model_config = {"from_attributes": True}


# -- Intro messages --


class IntroRequestCreate(BaseModel):
    contact_id: uuid.UUID
    match_result_id: uuid.UUID | None = None
    job_opening_id: uuid.UUID | None = None
    context: str | None = None
    tone: str = "professional"
    channel: str = "linkedin"


class IntroMessageResponse(BaseModel):
    id: uuid.UUID
    variant_label: str | None = None
    subject_line: str | None = None
    message_body: str
    sequence_step: int | None = None
    step_label: str | None = None
    send_after_days: int | None = 0
    coaching_notes: str | None = None
    is_selected: bool | None = False
    user_edited_body: str | None = None
    ai_model_version: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class IntroRequestResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    contact_id: uuid.UUID
    match_result_id: uuid.UUID | None = None
    job_opening_id: uuid.UUID | None = None
    context: str | None = None
    tone: str | None = None
    channel: str | None = None
    status: str
    messages: list[IntroMessageResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class IntroMessageUpdate(BaseModel):
    is_selected: bool | None = None
    user_edited_body: str | None = None
