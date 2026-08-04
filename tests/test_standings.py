from datetime import date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competition import Competition, CompetitionFormat, CompetitionLevel, Season, Stage
from app.models.match import Match, MatchPeriod, MatchStatus
from app.models.team import Team
from app.services.standings import StandingsService


@pytest.mark.asyncio
async def test_standings_computation(db_session: AsyncSession):
    competition = Competition(
        name="Test League", country="Ethiopia",
        level=CompetitionLevel.LOCAL, format=CompetitionFormat.LEAGUE,
    )
    db_session.add(competition)
    await db_session.flush()

    season = Season(
        competition_id=competition.id, name="2024",
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31), is_active=True,
    )
    db_session.add(season)
    await db_session.flush()

    stage = Stage(season_id=season.id, name="Main", sort_order=0)
    db_session.add(stage)
    await db_session.flush()

    team_a = Team(name="Alpha FC", country="Ethiopia")
    team_b = Team(name="Beta United", country="Ethiopia")
    db_session.add_all([team_a, team_b])
    await db_session.flush()

    match = Match(
        stage_id=stage.id,
        home_team_id=team_a.id,
        away_team_id=team_b.id,
        kickoff_at=datetime(2024, 6, 1, 15, 0),
        status=MatchStatus.FULL_TIME,
        current_period=MatchPeriod.FULL_TIME,
        home_score=2,
        away_score=1,
    )
    db_session.add(match)
    await db_session.flush()

    svc = StandingsService(db_session)
    rows = await svc.compute_for_stage(stage.id)

    assert len(rows) == 2
    home_row = next(r for r in rows if r.team_id == team_a.id)
    away_row = next(r for r in rows if r.team_id == team_b.id)
    assert home_row.points == 3
    assert home_row.goal_difference == 1
    assert away_row.points == 0
    assert away_row.goal_difference == -1
