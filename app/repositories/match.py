from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.competition import Season, Stage
from app.models.match import LineupEntry, Match, MatchEvent, MatchStatus
from app.repositories.base import BaseRepository


def _match_relations():
    """Joined loads needed to enrich a match with team + competition names."""
    return (
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.stage)
        .joinedload(Stage.season)
        .joinedload(Season.competition),
    )


class MatchRepository(BaseRepository[Match]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, Match)

    async def get_with_relations(self, id: uuid.UUID) -> Match | None:
        stmt = (
            select(Match)
            .options(
                joinedload(Match.events),
                joinedload(Match.lineups),
                *_match_relations(),
            )
            .where(Match.id == id)
        )
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_with_enrich(self, id: uuid.UUID) -> Match | None:
        """Get a match with team + competition relations needed for _enrich_match."""
        stmt = select(Match).options(*_match_relations()).where(Match.id == id)
        result = await self.session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[Match]:
        stmt = select(Match).options(*_match_relations()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def list_by_date(self, match_date: date) -> list[Match]:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Africa/Addis_Ababa")
        start = datetime.combine(match_date, datetime.min.time()).replace(tzinfo=tz)
        end = datetime.combine(match_date, datetime.max.time()).replace(tzinfo=tz)
        stmt = (
            select(Match)
            .options(*_match_relations())
            .where(
                and_(
                    Match.kickoff_at >= start,
                    Match.kickoff_at <= end,
                )
            )
            .order_by(Match.kickoff_at)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def list_live(self) -> list[Match]:
        stmt = (
            select(Match)
            .options(*_match_relations())
            .where(
                Match.status.in_([
                    MatchStatus.LIVE,
                    MatchStatus.HALF_TIME,
                    MatchStatus.EXTRA_TIME,
                    MatchStatus.PENALTIES,
                ])
            )
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def list_by_team(self, team_id: uuid.UUID, limit: int = 20) -> list[Match]:
        stmt = (
            select(Match)
            .options(*_match_relations())
            .where(
                or_(Match.home_team_id == team_id, Match.away_team_id == team_id)
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())

    async def list_by_stage(self, stage_id: uuid.UUID) -> list[Match]:
        stmt = (
            select(Match)
            .options(*_match_relations())
            .where(Match.stage_id == stage_id)
            .order_by(Match.kickoff_at)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


class MatchEventRepository(BaseRepository[MatchEvent]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, MatchEvent)

    async def list_by_match(self, match_id: uuid.UUID) -> list[MatchEvent]:
        stmt = (
            select(MatchEvent)
            .options(
                selectinload(MatchEvent.player),
                selectinload(MatchEvent.assist_player),
                selectinload(MatchEvent.player_off),
                selectinload(MatchEvent.player_on),
            )
            .where(MatchEvent.match_id == match_id)
            .order_by(MatchEvent.minute, MatchEvent.sequence)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())


class LineupEntryRepository(BaseRepository[LineupEntry]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, LineupEntry)

    async def list_by_match(self, match_id: uuid.UUID) -> list[LineupEntry]:
        stmt = (
            select(LineupEntry)
            .options(selectinload(LineupEntry.player))
            .where(LineupEntry.match_id == match_id)
            .order_by(LineupEntry.formation_place)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
