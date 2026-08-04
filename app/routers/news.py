from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.news import ArticleStatus
from app.models.user import User, UserRole
from app.repositories.news import ArticleRepository
from app.schemas.news import ArticleCreate, ArticleResponse, ArticleUpdate
from app.services.auth import require_role
from app.services.sse import sse_service

router = APIRouter(prefix="/api/v1/news", tags=["News"])


def _slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "article"


@router.get("", response_model=list[ArticleResponse])
async def list_articles(
    category: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = ArticleRepository(db)
    if category:
        return await repo.list_by_category(category)
    return await repo.list()


@router.get("/featured", response_model=list[ArticleResponse])
async def list_featured_articles(db: AsyncSession = Depends(get_db)):
    """Featured published articles — the path the mobile app calls."""
    repo = ArticleRepository(db)
    return await repo.list_featured()


@router.get("/{article_id}", response_model=ArticleResponse)
async def get_article(article_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = ArticleRepository(db)
    article = await repo.get(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return article


@router.post("", response_model=ArticleResponse, status_code=201)
async def create_article(
    body: ArticleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = ArticleRepository(db)
    slug = _slugify(body.title)
    existing = await repo.get_by_slug(slug)
    if existing:
        slug = f"{slug}-{uuid.uuid4().hex[:8]}"
    article = await repo.create(
        **body.model_dump(),
        slug=slug,
        author_id=current_user.id,
    )
    await sse_service.broadcast_change("news", "created", str(article.id))
    return article


@router.patch("/{article_id}", response_model=ArticleResponse)
async def update_article(
    article_id: uuid.UUID,
    body: ArticleUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = ArticleRepository(db)
    updates = body.model_dump(exclude_none=True)
    if "status" in updates and isinstance(updates["status"], str):
        try:
            updates["status"] = ArticleStatus(updates["status"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid status: {updates['status']}")
    if "category" in updates and isinstance(updates["category"], str):
        from app.models.news import NewsCategory
        try:
            updates["category"] = NewsCategory(updates["category"])
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid category: {updates['category']}")
    article = await repo.update(article_id, **updates)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    await sse_service.broadcast_change("news", "updated", str(article.id))
    if article.status == ArticleStatus.PUBLISHED:
        await sse_service.publish(
            sse_service.CHANNEL_NEWS,
            {"id": str(article.id), "title": article.title, "category": article.category.value},
        )
    return article


@router.delete("/{article_id}", status_code=204)
async def delete_article(
    article_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = ArticleRepository(db)
    deleted = await repo.delete(article_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Article not found")
    await sse_service.broadcast_change("news", "deleted", str(article_id))
