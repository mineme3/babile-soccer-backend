from __future__ import annotations

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.match import Match


class CompetitionLevel(enum.StrEnum):
    REGIONAL = "regional"
    ZONE = "zone"
    WOREDA = "woreda"
    LOCAL = "local"
    GRASSROOTS = "grassroots"


class CompetitionFormat(enum.StrEnum):
    LEAGUE = "league"
    GROUP_KNOCKOUT = "group_knockout"
    KNOCKOUT = "knockout"


class Competition(Base, TimestampMixin):
    __tablename__ = "competitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50))
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    zone_region: Mapped[str | None] = mapped_column(String(255))
    level: Mapped[CompetitionLevel] = mapped_column(SAEnum(CompetitionLevel), nullable=False)
    format: Mapped[CompetitionFormat] = mapped_column(SAEnum(CompetitionFormat), nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(1024))
    tier: Mapped[int] = mapped_column(Integer, default=1)

    seasons: Mapped[list[Season]] = relationship(back_populates="competition", cascade="all, delete-orphan")


class Season(Base, TimestampMixin):
    __tablename__ = "seasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    competition_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("competitions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[Date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Date] = mapped_column(Date, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=False)

    competition: Mapped[Competition] = relationship(back_populates="seasons")
    stages: Mapped[list[Stage]] = relationship(back_populates="season", cascade="all, delete-orphan")


class Stage(Base, TimestampMixin):
    __tablename__ = "stages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    season: Mapped[Season] = relationship(back_populates="stages")
    groups: Mapped[list[Group]] = relationship(back_populates="stage", cascade="all, delete-orphan")
    fixtures: Mapped[list[Match]] = relationship(back_populates="stage")


class Group(Base, TimestampMixin):
    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    min_age: Mapped[int | None] = mapped_column(Integer)
    max_age: Mapped[int | None] = mapped_column(Integer)

    stage: Mapped[Stage] = relationship(back_populates="groups")
