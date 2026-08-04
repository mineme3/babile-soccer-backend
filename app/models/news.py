from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.user import User


class NewsCategory(enum.StrEnum):
    MATCH_REPORT = "match_report"
    TRANSFER_RUMOUR = "transfer_rumour"
    TRANSFER_OFFICIAL = "transfer_official"
    PREVIEW = "preview"
    NEWS = "news"
    ANALYSIS = "analysis"


class ArticleStatus(enum.StrEnum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Article(Base, TimestampMixin):
    __tablename__ = "articles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    slug: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(String(1024))
    category: Mapped[NewsCategory] = mapped_column(SAEnum(NewsCategory), nullable=False)
    status: Mapped[ArticleStatus] = mapped_column(SAEnum(ArticleStatus), default=ArticleStatus.DRAFT, nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_featured: Mapped[bool] = mapped_column(default=False)

    author: Mapped[User] = relationship()
    tags: Mapped[list[ArticleTag]] = relationship(back_populates="article", cascade="all, delete-orphan")


class ArticleTag(Base, TimestampMixin):
    __tablename__ = "article_tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_uuid)
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("articles.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    article: Mapped[Article] = relationship(back_populates="tags")
