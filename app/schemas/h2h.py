import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class H2HMeetingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    match_id: uuid.UUID
    kickoff_at: datetime
    home_team: str | None = None
    away_team: str | None = None
    home_score: int
    away_score: int


class H2HResponse(BaseModel):
    team_a_id: uuid.UUID
    team_b_id: uuid.UUID
    total: int
    team_a_wins: int
    draws: int
    team_b_wins: int
    meetings: list[H2HMeetingResponse] = []
