from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.errors import classify_match_error, error_response, ErrorCode
from app.models.user import User, UserRole
from app.repositories.match import (
    LineupEntryRepository,
    MatchEventRepository,
    MatchRepository,
)
from app.schemas.match import (
    DisputeResolve,
    LineupEntryResponse,
    MatchCreate,
    MatchDetailResponse,
    MatchEventCreate,
    MatchEventResponse,
    MatchHydrationUpdate,
    MatchMinuteUpdate,
    MatchResponse,
    MatchStatisticsUpdate,
    MatchUpdate,
    ResultOnlyCreate,
)
from app.services.auth import require_role
from app.services.match import MatchService
from app.services.sse import sse_service
from app.services.standings import StandingsService

router = APIRouter(prefix="/api/v1/matches", tags=["Matches"])


def _enrich_match(match) -> dict:
    """Serialize a match with team + competition names for the app UI.

    This eagerly reads every attribute so the ORM session is no longer needed
    when FastAPI serialises the response — avoids MissingGreenlet errors on
    lazy-loaded ``updated_at`` / relationship columns.
    """
    stage = getattr(match, "stage", None)
    season = getattr(stage, "season", None) if stage else None
    competition = getattr(season, "competition", None) if season else None
    home_team = getattr(match, "home_team", None)
    away_team = getattr(match, "away_team", None)
    return {
        "id": match.id,
        "stage_id": match.stage_id,
        "group_id": match.group_id,
        "home_team_id": match.home_team_id,
        "away_team_id": match.away_team_id,
        "venue_name": match.venue_name,
        "referee_name": match.referee_name,
        "round": match.round,
        "kickoff_at": match.kickoff_at,
        "status": match.status,
        "current_period": match.current_period,
        "current_minute": match.current_minute,
        "added_time": match.added_time,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_penalties_score": match.home_penalties_score,
        "away_penalties_score": match.away_penalties_score,
        "data_tier": match.data_tier,
        "is_live_tracked": match.is_live_tracked,
        "is_result_only": match.is_result_only,
        "is_disputed": match.is_disputed,
        "record_status": match.record_status.value if match.record_status else None,
        "home_team_name": home_team.name if home_team else None,
        "away_team_name": away_team.name if away_team else None,
        "home_team_crest": getattr(home_team, "crest_url", None) if home_team else None,
        "away_team_crest": getattr(away_team, "crest_url", None) if away_team else None,
        "competition_name": competition.name if competition else None,
        "competition_logo": getattr(competition, "logo_url", None) if competition else None,
        "created_at": match.created_at,
        "updated_at": match.updated_at,
    }


@router.get("", response_model=list[MatchResponse])
async def list_matches(
    match_date: date | None = Query(None, alias="date"),
    stage_id: uuid.UUID | None = None,
    team_id: uuid.UUID | None = None,
    live_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    repo = MatchRepository(db)
    if live_only:
        matches = await repo.list_live()
    elif match_date:
        matches = await repo.list_by_date(match_date)
    elif stage_id:
        matches = await repo.list_by_stage(stage_id)
    elif team_id:
        matches = await repo.list_by_team(team_id)
    else:
        matches = await repo.list()
    return [_enrich_match(m) for m in matches]


@router.get("/date/{match_date}", response_model=list[MatchResponse])
async def list_matches_by_date(
    match_date: date,
    db: AsyncSession = Depends(get_db),
):
    """Matches for a specific date — the path the mobile app calls."""
    repo = MatchRepository(db)
    matches = await repo.list_by_date(match_date)
    return [_enrich_match(m) for m in matches]


@router.get("/live", response_model=list[MatchResponse])
async def list_live_matches(db: AsyncSession = Depends(get_db)):
    repo = MatchRepository(db)
    matches = await repo.list_live()
    return [_enrich_match(m) for m in matches]


@router.get("/{match_id}", response_model=MatchDetailResponse)
async def get_match(match_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = MatchRepository(db)
    match = await repo.get_with_relations(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    data = _enrich_match(match)
    data["events"] = [
        MatchEventResponse.model_validate(e) for e in (match.events or [])
    ]
    data["lineups"] = [
        LineupEntryResponse.model_validate(l) for l in (match.lineups or [])
    ]
    return data


@router.get("/{match_id}/events", response_model=list[MatchEventResponse])
async def get_match_events(match_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Events for a match — the path the app's Summary tab calls."""
    match_repo = MatchRepository(db)
    match = await match_repo.get(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    repo = MatchEventRepository(db)
    return await repo.list_by_match(match_id)


@router.get("/{match_id}/lineups", response_model=list[LineupEntryResponse])
async def get_match_lineups(match_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Line-ups for a match — the path the app's Line-ups tab calls."""
    match_repo = MatchRepository(db)
    match = await match_repo.get(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    repo = LineupEntryRepository(db)
    return await repo.list_by_match(match_id)


@router.post("", response_model=MatchResponse, status_code=201)
async def create_match(
    body: MatchCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.create_match(
            actor_id=user.id,
            **body.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    await sse_service.broadcast_change("match", "created", str(match.id))
    return _enrich_match(match)


@router.delete("/{match_id}", status_code=204)
async def delete_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        deleted = await svc.delete_match(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    if not deleted:
        return error_response(ErrorCode.MATCH_NOT_FOUND, "The requested match could not be found.", "Verify the match ID is correct.", 404)
    await sse_service.broadcast_change("match", "deleted", str(match_id))


@router.patch("/{match_id}", response_model=MatchResponse)
async def update_match(
    match_id: uuid.UUID,
    body: MatchUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = MatchRepository(db)
    match = await repo.update(match_id, **body.model_dump(exclude_none=True))
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    await sse_service.broadcast_change("match", "updated", str(match.id))
    return _enrich_match(match)


@router.get("/{match_id}/standings")
async def get_match_standings(match_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = MatchRepository(db)
    match = await repo.get(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    svc = StandingsService(db)
    rows = await svc.compute_for_stage(match.stage_id)
    return {"standings": rows}


@router.post("/{match_id}/events", response_model=MatchEventResponse, status_code=201)
async def add_match_event(
    match_id: uuid.UUID,
    body: MatchEventCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        return await svc.record_event(
            match_id=match_id,
            event_type=body.event_type,
            minute=body.minute,
            period=body.period,
            team_id=body.team_id,
            player_id=body.player_id,
            assist_player_id=body.assist_player_id,
            player_off_id=body.player_off_id,
            detail=body.detail,
            actor_id=user.id,
        )
    except ValueError as exc:
        msg = str(exc)
        status = 404 if "not found" in msg.lower() else 409
        raise HTTPException(status_code=status, detail=msg)


@router.post("/{match_id}/events/batch", response_model=list[MatchEventResponse], status_code=201)
async def sync_offline_events(
    match_id: uuid.UUID,
    events: list[MatchEventCreate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Offline-first sync: replay queued events in order (poor-network fallback)."""
    svc = MatchService(db)
    return await svc.sync_events(
        match_id,
        [e.model_dump() for e in events],
        actor_id=user.id,
    )


def _match_error_response(exc: ValueError):
    """Turn a MatchService ValueError into a structured error response."""
    return classify_match_error(exc)


@router.post("/{match_id}/lineups", response_model=list[LineupEntryResponse], status_code=201)
async def submit_lineup(
    match_id: uuid.UUID,
    team_id: uuid.UUID,
    player_ids: list[uuid.UUID],
    is_starting_xi: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        return await svc.submit_lineup(match_id, team_id, player_ids, is_starting_xi)
    except ValueError as exc:
        raise HTTPException(status_code=_match_error_status(exc), detail=str(exc))


@router.post("/{match_id}/start", response_model=MatchResponse)
async def start_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.start_match(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/half-time", response_model=MatchResponse)
async def half_time(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_half_time(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/second-half", response_model=MatchResponse)
async def second_half(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_second_half(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/extra-time", response_model=MatchResponse)
async def extra_time(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_extra_time(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/penalties", response_model=MatchResponse)
async def penalties(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_penalties(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/postponed", response_model=MatchResponse)
async def postponed(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_postponed(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/cancelled", response_model=MatchResponse)
async def cancelled(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_cancelled(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/abandoned", response_model=MatchResponse)
async def abandoned(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_abandoned(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/walkover", response_model=MatchResponse)
async def walkover(
    match_id: uuid.UUID,
    forfeiting_team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_walkover(match_id, actor_id=user.id)
        match.forfeiting_team_id = forfeiting_team_id
        await db.flush()
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/minute", response_model=MatchResponse)
async def sync_minute(
    match_id: uuid.UUID,
    body: MatchMinuteUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Client-authoritative minute sync from the operator console ticker."""
    svc = MatchService(db)
    try:
        match = await svc.sync_minute(
            match_id,
            minute=body.current_minute,
            period=body.current_period,
        )
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/hydration-break", response_model=MatchResponse)
async def hydration_break(
    match_id: uuid.UUID,
    body: MatchHydrationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_hydration_break(match_id, body.active, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/full-time", response_model=MatchResponse)
async def full_time(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.set_full_time(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/result-only", response_model=MatchResponse)
async def submit_result_only(
    match_id: uuid.UUID,
    body: ResultOnlyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.submit_result_only(
            match_id,
            home_score=body.home_score,
            away_score=body.away_score,
            scorers=[s.model_dump() for s in (body.scorers or [])],
            actor_id=user.id,
        )
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/statistics")
async def set_statistics(
    match_id: uuid.UUID,
    body: MatchStatisticsUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        await svc.set_statistics(match_id, team_id=body.team_id, stats=body.statistics)
    except ValueError as exc:
        return _match_error_response(exc)
    return await svc.get_statistics(match_id)


@router.get("/{match_id}/statistics")
async def get_statistics(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    match_repo = MatchRepository(db)
    match = await match_repo.get(match_id)
    if not match:
        return error_response(ErrorCode.MATCH_NOT_FOUND, "The requested match could not be found.", "Verify the match ID is correct.", 404)
    svc = MatchService(db)
    return await svc.get_statistics(match_id)


@router.post("/{match_id}/dispute", response_model=MatchResponse)
async def dispute_match(
    match_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.dispute_match(match_id, actor_id=user.id)
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)


@router.post("/{match_id}/resolve-dispute", response_model=MatchResponse)
async def resolve_dispute(
    match_id: uuid.UUID,
    body: DisputeResolve,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    svc = MatchService(db)
    try:
        match = await svc.resolve_dispute(
            match_id,
            home_score=body.home_score,
            away_score=body.away_score,
            actor_id=user.id,
        )
    except ValueError as exc:
        return _match_error_response(exc)
    return _enrich_match(match)
