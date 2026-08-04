from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import Match, MatchStatus


@dataclass
class StandingsRow:
    team_id: uuid.UUID
    team_name: str
    team_crest: str | None
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    goal_difference: int = 0
    points: int = 0
    deduction: int = 0
    form: list[str] = None
    rank: int = 0

    def __post_init__(self):
        self.form = self.form or []

    @property
    def net_points(self) -> int:
        return self.points - self.deduction


class StandingsService:
    """Computes league tables from confirmed match results — never hand-edited (FR-3.2)."""

    # Default tiebreaker chain per SRS FR-3.2: GD → GF → (H2H) → draw.
    def __init__(self, session: AsyncSession):
        self.session = session

    async def compute_for_stage(
        self,
        stage_id: uuid.UUID,
        group_id: uuid.UUID | None = None,
    ) -> list[StandingsRow]:
        matches = await self._get_confirmed_matches(stage_id, group_id)
        team_map: dict[uuid.UUID, StandingsRow] = {}

        for match in matches:
            if match.status == MatchStatus.WALKOVER:
                self._apply_walkover(team_map, match)
                continue

            home_id = match.home_team_id
            away_id = match.away_team_id
            home = team_map.setdefault(
                home_id,
                StandingsRow(
                    team_id=home_id,
                    team_name=getattr(match.home_team, "name", str(home_id)),
                    team_crest=getattr(match.home_team, "crest_url", None),
                ),
            )
            away = team_map.setdefault(
                away_id,
                StandingsRow(
                    team_id=away_id,
                    team_name=getattr(match.away_team, "name", str(away_id)),
                    team_crest=getattr(match.away_team, "crest_url", None),
                ),
            )

            home.played += 1
            away.played += 1
            home.goals_for += match.home_score
            home.goals_against += match.away_score
            away.goals_for += match.away_score
            away.goals_against += match.home_score

            if match.home_score > match.away_score:
                home.won += 1
                away.lost += 1
                home.points += 3
                home.form.append("W")
                away.form.append("L")
            elif match.home_score < match.away_score:
                home.lost += 1
                away.won += 1
                away.points += 3
                home.form.append("L")
                away.form.append("W")
            else:
                home.drawn += 1
                away.drawn += 1
                home.points += 1
                away.points += 1
                home.form.append("D")
                away.form.append("D")

        for row in team_map.values():
            row.goal_difference = row.goals_for - row.goals_against

        sorted_rows = sorted(
            team_map.values(),
            key=lambda r: (
                r.net_points,
                r.goal_difference,
                r.goals_for,
                r.team_name.lower(),
            ),
            reverse=True,
        )
        for i, row in enumerate(sorted_rows):
            row.rank = i + 1
        return sorted_rows

    def _apply_walkover(self, team_map: dict[uuid.UUID, StandingsRow], match: Match) -> None:
        """A walkover awards the opponent the win with a standard scoreline (e.g. 3-0)."""
        forfeiter_id = getattr(match, "forfeiting_team_id", None)
        # If a forfeiting team is flagged, award the other side; otherwise treat
        # the losing side of the recorded (default 3-0) scoreline as forfeiter.
        if forfeiter_id and forfeiter_id == match.home_team_id:
            winner, loser, ws, ls = match.away_team_id, match.home_team_id, match.away_score, match.home_score
        elif forfeiter_id and forfeiter_id == match.away_team_id:
            winner, loser, ws, ls = match.home_team_id, match.away_team_id, match.home_score, match.away_score
        elif match.home_score >= match.away_score:
            winner, loser, ws, ls = match.home_team_id, match.away_team_id, match.home_score, match.away_score
        else:
            winner, loser, ws, ls = match.away_team_id, match.home_team_id, match.away_score, match.home_score

        for team_id, name, crest in (
            (winner, getattr(match.home_team, "name", None) if winner == match.home_team_id else getattr(match.away_team, "name", None), None),
            (loser, getattr(match.home_team, "name", None) if loser == match.home_team_id else getattr(match.away_team, "name", None), None),
        ):
            team_map.setdefault(
                team_id,
                StandingsRow(team_id=team_id, team_name=str(name) if name else str(team_id), team_crest=crest),
            )

        team_map[winner].played += 1
        team_map[winner].won += 1
        team_map[winner].points += 3
        team_map[winner].goals_for += ws
        team_map[winner].goals_against += ls
        team_map[winner].form.append("W")

        team_map[loser].played += 1
        team_map[loser].lost += 1
        team_map[loser].goals_for += ls
        team_map[loser].goals_against += ws
        team_map[loser].form.append("L")

    async def _get_confirmed_matches(
        self,
        stage_id: uuid.UUID,
        group_id: uuid.UUID | None,
    ) -> list[Match]:
        from sqlalchemy.orm import joinedload

        stmt = (
            select(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .where(
                and_(
                    Match.stage_id == stage_id,
                    or_(
                        Match.status == MatchStatus.FULL_TIME,
                        Match.status == MatchStatus.WALKOVER,
                    ),
                )
            )
        )
        if group_id:
            stmt = stmt.where(Match.group_id == group_id)
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
