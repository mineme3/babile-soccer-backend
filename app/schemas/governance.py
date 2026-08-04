import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    reason: str | None = None
    diff: str | None = None
    actor_id: uuid.UUID
    created_at: datetime


class ModerationItemCreate(BaseModel):
    item_type: str = "wrong_score"
    entity_type: str
    entity_id: uuid.UUID
    payload: dict | None = None


class ModerationItemReview(BaseModel):
    status: str  # accepted | dismissed


class ModerationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    item_type: str
    entity_type: str
    entity_id: uuid.UUID
    payload: str | None = None
    status: str
    submitter_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
