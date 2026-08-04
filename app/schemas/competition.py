import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.competition import CompetitionFormat, CompetitionLevel


class CompetitionBase(BaseModel):
    name: str
    short_name: str | None = None
    country: str
    zone_region: str | None = None
    level: CompetitionLevel = CompetitionLevel.LOCAL
    format: CompetitionFormat = CompetitionFormat.LEAGUE
    logo_url: str | None = None
    tier: int = 1


class CompetitionCreate(CompetitionBase):
    pass


class CompetitionUpdate(BaseModel):
    name: str | None = None
    short_name: str | None = None
    country: str | None = None
    zone_region: str | None = None
    level: CompetitionLevel | None = None
    format: CompetitionFormat | None = None
    logo_url: str | None = None


class CompetitionResponse(CompetitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Flat responses (for CRUD endpoints — no nested children) ──

class SeasonBase(BaseModel):
    competition_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool = False


class SeasonCreate(SeasonBase):
    pass


class SeasonResponse(SeasonBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class StageBase(BaseModel):
    season_id: uuid.UUID
    name: str
    sort_order: int = 0


class StageCreate(StageBase):
    pass


class StageResponse(StageBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class GroupBase(BaseModel):
    stage_id: uuid.UUID
    name: str
    min_age: int | None = None
    max_age: int | None = None


class GroupCreate(GroupBase):
    pass


class GroupUpdate(BaseModel):
    name: str | None = None
    min_age: int | None = None
    max_age: int | None = None


class GroupResponse(GroupBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


# ── Nested responses (for /structure endpoint — full tree) ──

class GroupNest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    min_age: int | None = None
    max_age: int | None = None


class StageNest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    sort_order: int = 0
    groups: list[GroupNest] = []


class SeasonNest(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    competition_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_active: bool = False
    stages: list[StageNest] = []


class CompetitionStructureResponse(CompetitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    seasons: list[SeasonNest] = []
