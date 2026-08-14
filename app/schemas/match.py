import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.match import EventPeriod, EventType, MatchPeriod, MatchStatus, RecordStatus


class MatchBase(BaseModel):
    stage_id: uuid.UUID
    group_id: uuid.UUID | None = None
    home_team_id: uuid.UUID
    away_team_id: uuid.UUID
    venue_name: str | None = None
    referee_name: str | None = None
    round: str | None = None
    kickoff_at: datetime


class MatchCreate(MatchBase):
    pass


class MatchUpdate(BaseModel):
    status: MatchStatus | None = None
    current_period: MatchPeriod | None = None
    current_minute: int | None = None
    added_time: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_penalties_score: int | None = None
    away_penalties_score: int | None = None


class MatchMinuteUpdate(BaseModel):
    current_minute: int
    current_period: MatchPeriod | None = None


class MatchHydrationUpdate(BaseModel):
    active: bool


class MatchStartRequest(BaseModel):
    announcement: str | None = None


class MatchEventBase(BaseModel):
    event_type: EventType
    minute: int
    added_minute: int | None = None
    period: EventPeriod | None = None
    team_id: uuid.UUID
    player_id: uuid.UUID | None = None
    assist_player_id: uuid.UUID | None = None
    player_off_id: uuid.UUID | None = None
    player_on_id: uuid.UUID | None = None
    detail: str | None = None

    @field_validator("minute")
    @classmethod
    def minute_must_be_valid(cls, v: int) -> int:
        if v < 0 or v > 210:
            raise ValueError("minute must be between 0 and 210")
        return v


class MatchEventCreate(MatchEventBase):
    pass


class MatchEventResponse(MatchEventBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    match_id: uuid.UUID
    sequence: int
    created_at: datetime


class LineupEntryBase(BaseModel):
    match_id: uuid.UUID
    team_id: uuid.UUID
    player_id: uuid.UUID
    is_starting_xi: bool = True
    jersey_number: int | None = None
    position: str | None = None
    formation_place: int | None = None


class LineupEntryCreate(LineupEntryBase):
    pass


class LineupEntryResponse(LineupEntryBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime


class MatchResponse(MatchBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: MatchStatus
    current_period: MatchPeriod
    current_minute: int
    added_time: int
    home_score: int
    away_score: int
    home_penalties_score: int | None = None
    away_penalties_score: int | None = None
    # Data-tier / governance fields (Section 6):
    data_tier: int = 3
    is_live_tracked: bool = True
    is_result_only: bool = False
    is_disputed: bool = False
    record_status: RecordStatus = RecordStatus.DRAFT
    # Client-facing enrichment (not stored on the match row):
    home_team_name: str | None = None
    away_team_name: str | None = None
    home_team_crest: str | None = None
    away_team_crest: str | None = None
    competition_name: str | None = None
    competition_logo: str | None = None
    created_at: datetime
    updated_at: datetime


class MatchDetailResponse(MatchResponse):
    events: list[MatchEventResponse] = []
    lineups: list[LineupEntryResponse] = []


class MatchStatisticsUpdate(BaseModel):
    team_id: uuid.UUID
    statistics: dict[str, str | int]


class ResultOnlyCreate(BaseModel):
    home_score: int
    away_score: int
    scorers: list[MatchEventCreate] | None = None


class DisputeResolve(BaseModel):
    home_score: int
    away_score: int
