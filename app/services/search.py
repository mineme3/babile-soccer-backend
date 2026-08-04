from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competition import Competition
from app.models.match import Match
from app.models.player import Player
from app.models.team import Team


class SearchService:
    """Postgres full-text search over teams, players, competitions, and matches.

    NOTE: This is an MVP implementation using Postgres tsvector. If search quality
    becomes a complaint, the upgrade path is Meilisearch or Typesense.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_all(
        self, query: str, limit: int = 10
    ) -> dict[str, list[dict[str, Any]]]:
        results: dict[str, list[dict[str, Any]]] = {
            "teams": [],
            "players": [],
            "competitions": [],
            "matches": [],
        }
        if not query or len(query.strip()) < 2:
            return results

        like_pattern = f"%{query}%"

        teams = await self._search_teams(like_pattern, limit)
        results["teams"] = [{"id": str(t.id), "name": t.name, "crest_url": t.crest_url} for t in teams]

        players = await self._search_players(like_pattern, limit)
        results["players"] = [
            {
                "id": str(p.id),
                "name": p.name,
                "team_id": str(p.team_id),
                "position": p.position.value if p.position else None,
            }
            for p in players
        ]

        competitions = await self._search_competitions(like_pattern, limit)
        results["competitions"] = [
            {"id": str(c.id), "name": c.name, "country": c.country, "level": c.level.value}
            for c in competitions
        ]

        matches = await self._search_matches(like_pattern, limit)
        results["matches"] = [
            {
                "id": str(m.id),
                "home_team": m.home_team.name if m.home_team else None,
                "away_team": m.away_team.name if m.away_team else None,
                "home_score": m.home_score,
                "away_score": m.away_score,
                "status": m.status.value,
                "kickoff_at": m.kickoff_at.isoformat(),
            }
            for m in matches
        ]

        return results

    async def _search_teams(self, pattern: str, limit: int) -> list[Team]:
        from sqlalchemy import select
        stmt = select(Team).where(Team.name.ilike(pattern)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _search_players(self, pattern: str, limit: int) -> list[Player]:
        from sqlalchemy import select
        stmt = select(Player).where(Player.name.ilike(pattern)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _search_competitions(self, pattern: str, limit: int) -> list[Competition]:
        from sqlalchemy import select
        stmt = select(Competition).where(Competition.name.ilike(pattern)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _search_matches(self, pattern: str, limit: int) -> list[Match]:
        from sqlalchemy import or_, select
        from sqlalchemy.orm import joinedload

        stmt = (
            select(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .where(
                or_(
                    Match.home_team.has(Team.name.ilike(pattern)),
                    Match.away_team.has(Team.name.ilike(pattern)),
                )
            )
            .order_by(Match.kickoff_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.unique().scalars().all())
