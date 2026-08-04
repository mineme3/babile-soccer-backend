from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.match import Match, MatchStatus
from app.models.news import Article
from app.models.player import Player
from app.models.team import Team
from app.models.user import User, UserRole
from app.repositories.governance import AuditLogRepository
from app.schemas.governance import AuditLogResponse
from app.services.auth import require_role

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


@router.get("/dashboard")
async def get_admin_dashboard(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    teams_count = (await db.execute(select(func.count(Team.id)))).scalar() or 0
    players_count = (await db.execute(select(func.count(Player.id)))).scalar() or 0
    matches_count = (await db.execute(select(func.count(Match.id)))).scalar() or 0
    live_matches_count = (
        await db.execute(
            select(func.count(Match.id)).where(
                Match.status == MatchStatus.LIVE
            )
        )
    ).scalar() or 0
    news_count = (await db.execute(select(func.count(Article.id)))).scalar() or 0

    return {
        "teams_count": teams_count,
        "players_count": players_count,
        "matches_count": matches_count,
        "live_matches_count": live_matches_count,
        "news_count": news_count,
    }


@router.get("/audit", response_model=list[AuditLogResponse])
async def get_audit_logs(
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    """Full audit log of staff/admin mutations (FR-12.4)."""
    repo = AuditLogRepository(db)
    if entity_type and entity_id:
        return await repo.list_for_entity(entity_type, entity_id)
    return await repo.list_recent()
