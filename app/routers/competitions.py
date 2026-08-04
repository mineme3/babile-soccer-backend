from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.database import get_db
from app.models.competition import Season
from app.models.user import User, UserRole
from app.repositories.competition import (
    CompetitionRepository,
    GroupRepository,
    SeasonRepository,
    StageRepository,
)
from app.schemas.competition import (
    CompetitionCreate,
    CompetitionResponse,
    CompetitionStructureResponse,
    CompetitionUpdate,
    GroupCreate,
    GroupResponse,
    GroupUpdate,
    SeasonCreate,
    SeasonResponse,
    StageCreate,
    StageResponse,
)
from app.services.auth import require_role
from app.services.sse import sse_service
from app.services.standings import StandingsService

router = APIRouter(prefix="/api/v1/competitions", tags=["Competitions"])


@router.get("", response_model=list[CompetitionResponse])
async def list_competitions(
    level: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    repo = CompetitionRepository(db)
    if level:
        return await repo.list_by_level(level)
    return await repo.list()


@router.get("/{competition_id}", response_model=CompetitionResponse)
async def get_competition(competition_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = CompetitionRepository(db)
    comp = await repo.get_with_seasons(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp


@router.get("/{competition_id}/structure", response_model=CompetitionStructureResponse)
async def get_competition_structure(competition_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Competition with the full season → stage → group tree (admin dashboard)."""
    repo = CompetitionRepository(db)
    comp = await repo.get_with_structure(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    return comp


@router.post("", response_model=CompetitionResponse, status_code=201)
async def create_competition(
    body: CompetitionCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = CompetitionRepository(db)
    comp = await repo.create(**body.model_dump())
    await sse_service.broadcast_change("competition", "created", str(comp.id))
    return comp


@router.patch("/{competition_id}", response_model=CompetitionResponse)
async def update_competition(
    competition_id: uuid.UUID,
    body: CompetitionUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = CompetitionRepository(db)
    comp = await repo.update(competition_id, **body.model_dump(exclude_none=True))
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    await sse_service.broadcast_change("competition", "updated", str(comp.id))
    return comp


@router.get("/{competition_id}/standings")
async def get_standings(
    competition_id: uuid.UUID,
    season_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    if stage_id:
        svc = StandingsService(db)
        return await svc.compute_for_stage(stage_id)

    season_repo = SeasonRepository(db)
    if season_id:
        season = await season_repo.get(season_id)
    else:
        season = await season_repo.get_active_for_competition(competition_id)

    if not season:
        # The app resolves the standings tab from the match's stage id and
        # passes it here as the path param (stage-id proxy). Resolve it to
        # a stage and compute that stage's standings directly.
        stage_repo = StageRepository(db)
        stage = await stage_repo.get(competition_id)
        if stage:
            svc = StandingsService(db)
            return await svc.compute_for_stage(stage.id)
        raise HTTPException(status_code=404, detail="No active season found")

    stmt = select(Season).options(joinedload(Season.stages)).where(Season.id == season.id)
    result = await db.execute(stmt)
    season = result.unique().scalar_one_or_none()

    all_rows = []
    svc = StandingsService(db)
    for stage in (season.stages or []):
        all_rows.extend(await svc.compute_for_stage(stage.id))
    return all_rows


@router.post("/{competition_id}/seasons", response_model=SeasonResponse, status_code=201)
async def create_season(
    competition_id: uuid.UUID,
    body: SeasonCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    comp_repo = CompetitionRepository(db)
    comp = await comp_repo.get(competition_id)
    if not comp:
        raise HTTPException(status_code=404, detail="Competition not found")
    if body.competition_id != competition_id:
        raise HTTPException(status_code=400, detail="competition_id in body must match the URL")
    repo = SeasonRepository(db)
    season = await repo.create(**body.model_dump())
    await sse_service.broadcast_change("season", "created", str(season.id))
    return season


@router.post("/{competition_id}/stages", response_model=StageResponse, status_code=201)
async def create_stage(
    competition_id: uuid.UUID,
    body: StageCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    season_repo = SeasonRepository(db)
    season = await season_repo.get(body.season_id)
    if not season or season.competition_id != competition_id:
        raise HTTPException(status_code=404, detail="Season not found in this competition")
    repo = StageRepository(db)
    stage = await repo.create(**body.model_dump())
    await sse_service.broadcast_change("stage", "created", str(stage.id))
    return stage


@router.post("/{competition_id}/groups", response_model=GroupResponse, status_code=201)
async def create_group(
    competition_id: uuid.UUID,
    body: GroupCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    stage_repo = StageRepository(db)
    stage = await stage_repo.get(body.stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    season_repo = SeasonRepository(db)
    season = await season_repo.get(stage.season_id)
    if not season or season.competition_id != competition_id:
        raise HTTPException(status_code=404, detail="Stage does not belong to this competition")
    repo = GroupRepository(db)
    group = await repo.create(**body.model_dump())
    await sse_service.broadcast_change("group", "created", str(group.id))
    return group


@router.delete("/{competition_id}", status_code=204)
async def delete_competition(
    competition_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = CompetitionRepository(db)
    deleted = await repo.delete(competition_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Competition not found")
    await sse_service.broadcast_change("competition", "deleted", str(competition_id))


@router.delete("/{competition_id}/seasons/{season_id}", status_code=204)
async def delete_season(
    competition_id: uuid.UUID,
    season_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = SeasonRepository(db)
    season = await repo.get(season_id)
    if not season or season.competition_id != competition_id:
        raise HTTPException(status_code=404, detail="Season not found in this competition")
    deleted = await repo.delete(season_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Season not found")
    await sse_service.broadcast_change("season", "deleted", str(season_id))


@router.delete("/{competition_id}/stages/{stage_id}", status_code=204)
async def delete_stage(
    competition_id: uuid.UUID,
    stage_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    stage_repo = StageRepository(db)
    stage = await stage_repo.get(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    season_repo = SeasonRepository(db)
    season = await season_repo.get(stage.season_id)
    if not season or season.competition_id != competition_id:
        raise HTTPException(status_code=404, detail="Stage does not belong to this competition")
    deleted = await stage_repo.delete(stage_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Stage not found")
    await sse_service.broadcast_change("stage", "deleted", str(stage_id))


@router.patch("/{competition_id}/groups/{group_id}", response_model=GroupResponse)
async def update_group(
    competition_id: uuid.UUID,
    group_id: uuid.UUID,
    body: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = GroupRepository(db)
    group = await repo.update(group_id, **body.model_dump(exclude_none=True))
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    await sse_service.broadcast_change("group", "updated", str(group.id))
    return group


@router.delete("/{competition_id}/groups/{group_id}", status_code=204)
async def delete_group(
    competition_id: uuid.UUID,
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    group_repo = GroupRepository(db)
    group = await group_repo.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    stage_repo = StageRepository(db)
    stage = await stage_repo.get(group.stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail="Stage not found")
    season_repo = SeasonRepository(db)
    season = await season_repo.get(stage.season_id)
    if not season or season.competition_id != competition_id:
        raise HTTPException(status_code=404, detail="Group does not belong to this competition")
    deleted = await group_repo.delete(group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Group not found")
    await sse_service.broadcast_change("group", "deleted", str(group_id))
