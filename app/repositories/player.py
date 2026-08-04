import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.player import Player
from app.repositories.base import BaseRepository


class PlayerRepository(BaseRepository[Player]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Player)

    async def list_by_team(self, team_id: uuid.UUID) -> list[Player]:
        stmt = select(Player).where(Player.team_id == team_id).order_by(Player.jersey_number)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_team_and_jersey(
        self,
        team_id: uuid.UUID,
        jersey_number: int,
        exclude_id: uuid.UUID | None = None,
    ) -> Player | None:
        """A player on this team already wearing this jersey number."""
        if jersey_number is None:
            return None
        stmt = select(Player).where(
            Player.team_id == team_id,
            Player.jersey_number == jersey_number,
        )
        if exclude_id is not None:
            stmt = stmt.where(Player.id != exclude_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
