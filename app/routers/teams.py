from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.repositories.match import MatchRepository
from app.repositories.player import PlayerRepository
from app.repositories.team import TeamRepository
from app.schemas.h2h import H2HResponse
from app.schemas.match import MatchResponse
from app.schemas.player import PlayerResponse
from app.schemas.team import TeamCreate, TeamResponse, TeamUpdate
from app.services.auth import require_role
from app.services.h2h import HeadToHeadService

router = APIRouter(prefix="/api/v1/teams", tags=["Teams"])


@router.get("", response_model=list[TeamResponse])
async def list_teams(db: AsyncSession = Depends(get_db)):
    repo = TeamRepository(db)
    return await repo.list()


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = TeamRepository(db)
    team = await repo.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.post("", response_model=TeamResponse, status_code=201)
async def create_team(
    body: TeamCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = TeamRepository(db)
    team = await repo.create(**body.model_dump())
    return team


@router.patch("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: uuid.UUID,
    body: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = TeamRepository(db)
    team = await repo.update(team_id, **body.model_dump(exclude_none=True))
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.delete("/{team_id}", status_code=204)
async def delete_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = TeamRepository(db)
    team = await repo.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    deleted = await repo.delete(team_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Team not found")


@router.get("/{team_id}/h2h/{opponent_id}", response_model=H2HResponse)
async def head_to_head(
    team_id: uuid.UUID,
    opponent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = TeamRepository(db)
    team = await repo.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    opponent = await repo.get(opponent_id)
    if not opponent:
        raise HTTPException(status_code=404, detail="Opponent team not found")
    svc = HeadToHeadService(db)
    return await svc.compute(team_id, opponent_id)


@router.get("/{team_id}/matches", response_model=list[MatchResponse])
async def get_team_matches(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = TeamRepository(db)
    team = await repo.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    match_repo = MatchRepository(db)
    return await match_repo.list_by_team(team_id)


@router.get("/{team_id}/players", response_model=list[PlayerResponse])
async def get_team_players(team_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = TeamRepository(db)
    team = await repo.get(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    player_repo = PlayerRepository(db)
    return await player_repo.list_by_team(team_id)
