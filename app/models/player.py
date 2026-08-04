from __future__ import annotations

import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.team import Team


class PlayerPosition(enum.StrEnum):
    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"


class Player(Base, TimestampMixin):
    __tablename__ = "players"

    # A jersey number is unique within a team. Postgres treats NULLs as
    # distinct, so players without a number are never blocked by this.
    __table_args__ = (
        UniqueConstraint("team_id", "jersey_number", name="uq_players_team_jersey"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    team_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("teams.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jersey_number: Mapped[int | None] = mapped_column(Integer)
    position: Mapped[PlayerPosition | None] = mapped_column(SAEnum(PlayerPosition))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    nationality: Mapped[str | None] = mapped_column(String(100))
    photo_url: Mapped[str | None] = mapped_column(String(1024))
    is_injured: Mapped[bool] = mapped_column(default=False)
    is_suspended: Mapped[bool] = mapped_column(default=False)

    team: Mapped[Team] = relationship(back_populates="players")
