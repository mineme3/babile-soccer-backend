"""Head-to-head history between two teams (FR-2.7)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchStatus


@dataclass
class H2HMeeting:
    match_id: uuid.UUID
    kickoff_at: object
    home_team: str | None
    away_team: str | None
    home_score: int
    away_score: int


@dataclass
class H2HResult:
    team_a_id: uuid.UUID
    team_b_id: uuid.UUID
    total: int
    team_a_wins: int
    draws: int
    team_b_wins: int
    meetings: list[H2HMeeting]


class HeadToHeadService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute(self, team_a_id: uuid.UUID, team_b_id: uuid.UUID, limit: int = 10) -> H2HResult:
        from sqlalchemy.orm import joinedload

        stmt = (
            select(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .where(
                and_(
                    Match.status == MatchStatus.FULL_TIME,
                    or_(
                        and_(Match.home_team_id == team_a_id, Match.away_team_id == team_b_id),
                        and_(Match.home_team_id == team_b_id, Match.away_team_id == team_a_id),
                    ),
                )
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        matches = list(result.unique().scalars().all())

        team_a_wins = draws = team_b_wins = 0
        meetings: list[H2HMeeting] = []
        for m in matches:
            home_id, away_id = m.home_team_id, m.away_team_id
            if m.home_score > m.away_score:
                if home_id == team_a_id:
                    team_a_wins += 1
                else:
                    team_b_wins += 1
            elif m.home_score < m.away_score:
                if away_id == team_a_id:
                    team_a_wins += 1
                else:
                    team_b_wins += 1
            else:
                draws += 1
            meetings.append(
                H2HMeeting(
                    match_id=m.id,
                    kickoff_at=m.kickoff_at,
                    home_team=m.home_team.name if m.home_team else None,
                    away_team=m.away_team.name if m.away_team else None,
                    home_score=m.home_score,
                    away_score=m.away_score,
                )
            )

        return H2HResult(
            team_a_id=team_a_id,
            team_b_id=team_b_id,
            total=len(matches),
            team_a_wins=team_a_wins,
            draws=draws,
            team_b_wins=team_b_wins,
            meetings=meetings,
        )
