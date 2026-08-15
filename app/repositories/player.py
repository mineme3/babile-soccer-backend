from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.match import Match, MatchEvent, EventType, LineupEntry
from app.models.competition import Stage, Season
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

    async def get_stats(self, player_id: uuid.UUID) -> dict[str, Any]:
        """Aggregate player stats across all matches."""

        # Total goals (player is the scorer)
        goals_stmt = (
            select(func.count())
            .select_from(MatchEvent)
            .where(
                MatchEvent.player_id == player_id,
                MatchEvent.event_type.in_([EventType.GOAL, EventType.PENALTY_SCORED]),
            )
        )

        # Assists
        assists_stmt = (
            select(func.count())
            .select_from(MatchEvent)
            .where(MatchEvent.assist_player_id == player_id)
        )

        # Yellow cards
        yellow_stmt = (
            select(func.count())
            .select_from(MatchEvent)
            .where(
                MatchEvent.player_id == player_id,
                MatchEvent.event_type == EventType.YELLOW_CARD,
            )
        )

        # Red cards (direct red)
        red_stmt = (
            select(func.count())
            .select_from(MatchEvent)
            .where(
                MatchEvent.player_id == player_id,
                MatchEvent.event_type == EventType.RED_CARD,
            )
        )

        goals_result = await self.session.execute(goals_stmt)
        assists_result = await self.session.execute(assists_stmt)
        yellow_result = await self.session.execute(yellow_stmt)
        red_result = await self.session.execute(red_stmt)

        # Appearances and minutes from lineups + matches
        lineup_stmt = (
            select(LineupEntry, Match)
            .join(Match, LineupEntry.match_id == Match.id)
            .options(
                joinedload(Match.home_team),
                joinedload(Match.away_team),
                joinedload(Match.stage)
                .joinedload(Stage.season)
                .joinedload(Season.competition),
            )
            .where(LineupEntry.player_id == player_id)
        )
        lineup_result = await self.session.execute(lineup_stmt)
        lineup_rows = lineup_result.all()

        goals = goals_result.scalar_one() or 0
        assists = assists_result.scalar_one() or 0
        yellow = yellow_result.scalar_one() or 0
        red = red_result.scalar_one() or 0

        appearances = len(lineup_rows)

        # Build recent_matches list from matches where player appeared
        recent_matches: list[dict[str, Any]] = []
        for row in sorted(lineup_rows, key=lambda r: r.Match.kickoff_at, reverse=True)[:5]:
            m = row.Match
            recent_matches.append(
                {
                    "id": str(m.id),
                    "home_team_id": str(m.home_team_id),
                    "away_team_id": str(m.away_team_id),
                    "home_team_name": m.home_team.name if m.home_team else None,
                    "away_team_name": m.away_team.name if m.away_team else None,
                    "home_score": m.home_score,
                    "away_score": m.away_score,
                    "status": m.status.value,
                    "current_minute": m.current_minute,
                    "kickoff_at": m.kickoff_at.isoformat(),
                    "competition_name": (
                        m.stage.season.competition.name
                        if m.stage and m.stage.season and m.stage.season.competition
                        else None
                    ),
                }
            )

        total_minutes = sum(getattr(row.Match, "current_minute", 0) for row in lineup_rows)

        return {
            "goals": goals,
            "assists": assists,
            "appearances": appearances,
            "minutes": total_minutes,
            "yellow_cards": yellow,
            "red_cards": red,
            "recent_matches": recent_matches,
        }
