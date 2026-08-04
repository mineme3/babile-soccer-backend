from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team
from app.repositories.base import BaseRepository


class TeamRepository(BaseRepository[Team]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Team)
