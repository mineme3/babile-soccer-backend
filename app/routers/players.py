from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.repositories.player import PlayerRepository
from app.repositories.team import TeamRepository
from app.schemas.player import PlayerCreate, PlayerResponse, PlayerUpdate
from app.services.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/players", tags=["Players"])


@router.get("", response_model=list[PlayerResponse])
async def list_players(db: AsyncSession = Depends(get_db)):
    repo = PlayerRepository(db)
    return await repo.list()


@router.get("/{player_id}", response_model=PlayerResponse)
async def get_player(player_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = PlayerRepository(db)
    player = await repo.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.get("/{player_id}/stats")
async def get_player_stats(player_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = PlayerRepository(db)
    player = await repo.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    stats = await repo.get_stats(player_id)
    return stats


@router.post("", response_model=PlayerResponse, status_code=201)
async def create_player(
    body: PlayerCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    team_repo = TeamRepository(db)
    team = await team_repo.get(body.team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    repo = PlayerRepository(db)
    if body.jersey_number is not None:
        existing = await repo.get_by_team_and_jersey(body.team_id, body.jersey_number)
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Jersey number {body.jersey_number} is already assigned "
                    f"to {existing.name} on this team."
                ),
            )
    player = await repo.create(**body.model_dump())
    return player


@router.patch("/{player_id}", response_model=PlayerResponse)
async def update_player(
    player_id: uuid.UUID,
    body: PlayerUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = PlayerRepository(db)
    player = await repo.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    update_data = body.model_dump(exclude_none=True)
    logger.info("Updating player %s with data: %s", player_id, update_data)
    jersey_number = update_data.get("jersey_number")
    if jersey_number is not None:
        existing = await repo.get_by_team_and_jersey(
            player.team_id, jersey_number, exclude_id=player_id
        )
        if existing:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Jersey number {jersey_number} is already assigned "
                    f"to {existing.name} on this team."
                ),
            )
    player = await repo.update(player_id, **update_data)
    return player


@router.delete("/{player_id}", status_code=204)
async def delete_player(
    player_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = PlayerRepository(db)
    player = await repo.get(player_id)
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    deleted = await repo.delete(player_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Player not found")
