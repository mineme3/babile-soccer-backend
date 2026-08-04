import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.player import PlayerPosition


class PlayerBase(BaseModel):
    team_id: uuid.UUID
    name: str
    jersey_number: int | None = None
    position: PlayerPosition | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    photo_url: str | None = None


class PlayerCreate(PlayerBase):
    pass


class PlayerUpdate(BaseModel):
    name: str | None = None
    jersey_number: int | None = None
    position: PlayerPosition | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    photo_url: str | None = None
    is_injured: bool | None = None
    is_suspended: bool | None = None


class PlayerResponse(PlayerBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_injured: bool
    is_suspended: bool
    created_at: datetime
    updated_at: datetime
