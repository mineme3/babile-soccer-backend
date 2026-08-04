from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.user import User


class AuditLog(Base, TimestampMixin):
    """Append-only record of every staff/admin mutation on match data (FR-12.4).

    Nothing is silently overwritten: any create/edit/delete on match data is
    recorded with the actor, action, and a JSON diff of before/after state.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255))
    diff: Mapped[dict | None] = mapped_column(Text)  # JSON string of before/after
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    actor: Mapped[User] = relationship()


class ModerationItem(Base, TimestampMixin):
    """Moderation queue for user-submitted reports and community tips (FR-2.9, 6.4).

    Never auto-applied: a Moderator/Competition Manager accepts or dismisses.
    """

    __tablename__ = "moderation_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    item_type: Mapped[str] = mapped_column(String(50), nullable=False)  # wrong_score | community_tip
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payload: Mapped[dict | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)  # open|accepted|dismissed
    submitter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    submitter: Mapped[User | None] = relationship(foreign_keys=[submitter_id])
    reviewer: Mapped[User | None] = relationship(foreign_keys=[reviewer_id])
