import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TeamBase(BaseModel):
    name: str
    short_name: str | None = None
    crest_url: str | None = None
    venue_name: str | None = None
    venue_capacity: int | None = None
    coach_name: str | None = None
    coach_photo_url: str | None = None
    country: str


class TeamCreate(TeamBase):
    pass


class TeamUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    crest_url: str | None = None
    venue_name: str | None = None
    venue_capacity: int | None = None
    coach_name: str | None = None
    coach_photo_url: str | None = None
    country: str | None = None


class TeamResponse(TeamBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
