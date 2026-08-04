import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.competition import Competition, Group, Season, Stage
from app.repositories.base import BaseRepository


class CompetitionRepository(BaseRepository[Competition]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Competition)

    async def get_with_seasons(self, id: uuid.UUID) -> Competition | None:
        stmt = select(Competition).options(joinedload(Competition.seasons)).where(Competition.id == id)
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_with_structure(self, id: uuid.UUID) -> Competition | None:
        stmt = (
            select(Competition)
            .options(
                joinedload(Competition.seasons)
                .joinedload(Season.stages)
                .joinedload(Stage.groups)
            )
            .where(Competition.id == id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list_by_level(self, level: str) -> list[Competition]:
        stmt = select(Competition).where(Competition.level == level)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SeasonRepository(BaseRepository[Season]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Season)

    async def get_active_for_competition(self, competition_id: uuid.UUID) -> Season | None:
        stmt = select(Season).where(
            Season.competition_id == competition_id,
            Season.is_active,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class StageRepository(BaseRepository[Stage]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Stage)


class GroupRepository(BaseRepository[Group]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Group)
