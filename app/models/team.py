from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.player import Player


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50))
    crest_url: Mapped[str | None] = mapped_column(String(1024))
    venue_name: Mapped[str | None] = mapped_column(String(255))
    venue_capacity: Mapped[int | None] = mapped_column(Integer)
    coach_name: Mapped[str | None] = mapped_column(String(255))
    coach_photo_url: Mapped[str | None] = mapped_column(String(1024))
    country: Mapped[str] = mapped_column(String(100), nullable=False)

    players: Mapped[list[Player]] = relationship(back_populates="team", cascade="all, delete-orphan")
    season_registrations: Mapped[list[TeamSeason]] = relationship(back_populates="team", cascade="all, delete-orphan")


class TeamSeason(Base, TimestampMixin):
    __tablename__ = "team_seasons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    season_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("seasons.id"), nullable=False)
    group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("groups.id"))

    team: Mapped[Team] = relationship(back_populates="season_registrations")
