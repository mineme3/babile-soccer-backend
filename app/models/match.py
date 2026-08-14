from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.competition import Stage
    from app.models.player import Player
    from app.models.team import Team


class MatchStatus(enum.StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    HALF_TIME = "half_time"
    FULL_TIME = "full_time"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"
    POSTPONED = "postponed"
    CANCELLED = "cancelled"
    ABANDONED = "abandoned"
    WALKOVER = "walkover"


class MatchPeriod(enum.StrEnum):
    NOT_STARTED = "not_started"
    FIRST_HALF = "first_half"
    HALF_TIME = "half_time"
    SECOND_HALF = "second_half"
    EXTRA_TIME = "extra_time"
    PENALTIES = "penalties"
    FULL_TIME = "full_time"


class RecordStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    DISPUTED = "disputed"
    RESOLVED = "resolved"
    PUBLISHED = "published"
    CORRECTED = "corrected"


class EventType(enum.StrEnum):
    GOAL = "goal"
    OWN_GOAL = "own_goal"
    PENALTY_SCORED = "penalty_scored"
    PENALTY_MISSED = "penalty_missed"
    YELLOW_CARD = "yellow_card"
    RED_CARD = "red_card"
    SUBSTITUTION = "substitution"


class EventPeriod(enum.StrEnum):
    FIRST_HALF = "1h"
    SECOND_HALF = "2h"
    EXTRA_TIME = "et"
    PENALTIES = "pens"


class Match(Base, TimestampMixin):
    __tablename__ = "matches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stages.id"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id"))
    home_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    away_team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    venue_name: Mapped[str | None] = mapped_column(String(255))
    referee_name: Mapped[str | None] = mapped_column(String(255))
    round: Mapped[str | None] = mapped_column(String(50))

    kickoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[MatchStatus] = mapped_column(SAEnum(MatchStatus), default=MatchStatus.SCHEDULED, nullable=False)
    current_period: Mapped[MatchPeriod] = mapped_column(
        SAEnum(MatchPeriod), default=MatchPeriod.NOT_STARTED, nullable=False
    )
    current_minute: Mapped[int] = mapped_column(Integer, default=0)
    added_time: Mapped[int] = mapped_column(Integer, default=0)

    home_score: Mapped[int] = mapped_column(Integer, default=0)
    away_score: Mapped[int] = mapped_column(Integer, default=0)
    home_penalties_score: Mapped[int | None] = mapped_column(Integer)
    away_penalties_score: Mapped[int | None] = mapped_column(Integer)

    # Tier-3 / data governance fields (Section 6 of the SRS)
    data_tier: Mapped[int] = mapped_column(Integer, default=3)
    is_live_tracked: Mapped[bool] = mapped_column(default=True)
    is_result_only: Mapped[bool] = mapped_column(default=False)
    is_disputed: Mapped[bool] = mapped_column(default=False)
    record_status: Mapped[RecordStatus] = mapped_column(
        SAEnum(RecordStatus), default=RecordStatus.DRAFT, nullable=False
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    forfeiting_team_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"))
    hydration_break_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    home_team: Mapped[Team] = relationship(foreign_keys=[home_team_id])
    away_team: Mapped[Team] = relationship(foreign_keys=[away_team_id])
    stage: Mapped[Stage] = relationship(back_populates="fixtures")
    events: Mapped[list[MatchEvent]] = relationship(back_populates="match", cascade="all, delete-orphan")
    lineups: Mapped[list[LineupEntry]] = relationship(back_populates="match", cascade="all, delete-orphan")
    statistics: Mapped[list[MatchStatistic]] = relationship(back_populates="match", cascade="all, delete-orphan")


class MatchEvent(Base, TimestampMixin):
    __tablename__ = "match_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), nullable=False)
    minute: Mapped[int] = mapped_column(Integer, nullable=False)
    added_minute: Mapped[int | None] = mapped_column(Integer)
    period: Mapped[EventPeriod] = mapped_column(
        SAEnum(EventPeriod), default=EventPeriod.FIRST_HALF, nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"))
    assist_player_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"))
    player_off_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"))
    player_on_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"))
    detail: Mapped[str | None] = mapped_column(Text)
    sequence: Mapped[int] = mapped_column(Integer, default=0)

    match: Mapped[Match] = relationship(back_populates="events")
    team: Mapped[Team] = relationship(foreign_keys=[team_id])
    player: Mapped[Player | None] = relationship(foreign_keys=[player_id])
    assist_player: Mapped[Player | None] = relationship(foreign_keys=[assist_player_id])
    player_off: Mapped[Player | None] = relationship(foreign_keys=[player_off_id])
    player_on: Mapped[Player | None] = relationship(foreign_keys=[player_on_id])


class LineupEntry(Base, TimestampMixin):
    __tablename__ = "lineup_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    player_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("players.id"), nullable=False)
    is_starting_xi: Mapped[bool] = mapped_column(default=True)
    jersey_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[str | None] = mapped_column(String(50))
    formation_place: Mapped[int | None] = mapped_column(Integer)

    match: Mapped[Match] = relationship(back_populates="lineups")
    team: Mapped[Team] = relationship()
    player: Mapped[Player] = relationship()


class MatchStatistic(Base, TimestampMixin):
    __tablename__ = "match_statistics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id"), nullable=False)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    stat_name: Mapped[str] = mapped_column(String(100), nullable=False)
    stat_value: Mapped[str] = mapped_column(String(50), nullable=False)

    match: Mapped[Match] = relationship(back_populates="statistics")
