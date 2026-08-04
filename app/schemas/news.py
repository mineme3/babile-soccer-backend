import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.news import ArticleStatus, NewsCategory


class ArticleBase(BaseModel):
    title: str
    excerpt: str | None = None
    content: str
    cover_image_url: str | None = None
    category: NewsCategory
    is_featured: bool = False


class ArticleCreate(ArticleBase):
    pass


class ArticleUpdate(BaseModel):
    title: str | None = None
    excerpt: str | None = None
    content: str | None = None
    cover_image_url: str | None = None
    category: NewsCategory | None = None
    status: ArticleStatus | None = None
    is_featured: bool | None = None


class ArticleResponse(ArticleBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    status: ArticleStatus
    author_id: uuid.UUID
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
