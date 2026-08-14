from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import Article, ArticleStatus, NewsCategory
from app.repositories.base import BaseRepository


class ArticleRepository(BaseRepository[Article]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Article)

    async def get_by_slug(self, slug: str) -> Article | None:
        stmt = select(Article).where(Article.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_category(self, category: str) -> list[Article]:
        try:
            cat_enum = NewsCategory(category)
        except ValueError:
            return []
        stmt = (
            select(Article)
            .where(Article.category == cat_enum)
            .order_by(Article.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_featured(self, limit: int = 10) -> list[Article]:
        stmt = (
            select(Article)
            .where(Article.is_featured.is_(True), Article.status == ArticleStatus.PUBLISHED)
            .order_by(Article.published_at.desc().nulls_last())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
