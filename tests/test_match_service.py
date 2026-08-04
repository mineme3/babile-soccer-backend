from datetime import date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.competition import Competition, CompetitionFormat, CompetitionLevel, Season, Stage
from app.models.match import EventType, Match, MatchPeriod, MatchStatus
from app.models.player import Player
from app.models.team import Team
from app.services.match import MatchService


@pytest.fixture
async def live_match(db_session: AsyncSession):
    competition = Competition(
        name="Cup", country="Ethiopia",
        level=CompetitionLevel.LOCAL, format=CompetitionFormat.KNOCKOUT,
    )
    db_session.add(competition)
    await db_session.flush()

    season = Season(
        competition_id=competition.id, name="2024",
        start_date=date(2024, 1, 1), end_date=date(2024, 12, 31),
    )
    db_session.add(season)
    await db_session.flush()

    stage = Stage(season_id=season.id, name="Final")
    db_session.add(stage)
    await db_session.flush()

    team_h = Team(name="Home", country="Ethiopia")
    team_a = Team(name="Away", country="Ethiopia")
    db_session.add_all([team_h, team_a])
    await db_session.flush()

    player = Player(team_id=team_h.id, name="Scorer")
    db_session.add(player)
    await db_session.flush()

    match = Match(
        stage_id=stage.id, home_team_id=team_h.id, away_team_id=team_a.id,
        kickoff_at=datetime(2024, 6, 1, 15, 0),
        status=MatchStatus.SCHEDULED, current_period=MatchPeriod.NOT_STARTED,
    )
    db_session.add(match)
    await db_session.flush()

    return {"match": match, "team_h": team_h, "team_a": team_a, "player": player}


@pytest.mark.asyncio
async def test_record_goal_updates_score(db_session: AsyncSession, live_match):
    svc = MatchService(db_session)
    match = live_match["match"]

    event = await svc.record_event(
        match_id=match.id,
        event_type=EventType.GOAL,
        minute=23,
        team_id=live_match["team_h"].id,
        player_id=live_match["player"].id,
    )
    assert event.event_type == EventType.GOAL
    assert event.minute == 23

    await db_session.refresh(match)
    assert match.home_score == 1
    assert match.away_score == 0


@pytest.mark.asyncio
async def test_match_status_lifecycle(db_session: AsyncSession, live_match):
    svc = MatchService(db_session)
    match = live_match["match"]

    await svc.start_match(match.id)
    await db_session.refresh(match)
    assert match.status == MatchStatus.LIVE
    assert match.current_period == MatchPeriod.FIRST_HALF

    await svc.set_half_time(match.id)
    await db_session.refresh(match)
    assert match.status == MatchStatus.HALF_TIME

    await svc.set_full_time(match.id)
    await db_session.refresh(match)
    assert match.status == MatchStatus.FULL_TIME


@pytest.mark.asyncio
async def test_submit_lineup_replaces_previous(db_session: AsyncSession, live_match):
    svc = MatchService(db_session)
    match = live_match["match"]

    await svc.submit_lineup(match.id, live_match["team_h"].id, [live_match["player"].id])
    await svc.submit_lineup(match.id, live_match["team_h"].id, [live_match["player"].id])

    from sqlalchemy import select

    from app.models.match import LineupEntry

    result = await db_session.execute(select(LineupEntry).where(LineupEntry.match_id == match.id))
    assert len(result.scalars().all()) == 1
