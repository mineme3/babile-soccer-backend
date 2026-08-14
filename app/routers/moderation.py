from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User, UserRole
from app.repositories.governance import ModerationRepository
from app.schemas.governance import ModerationItemCreate, ModerationItemResponse, ModerationItemReview

from app.services.auth import require_role

router = APIRouter(prefix="/api/v1/moderation", tags=["Moderation"])


@router.post("", response_model=ModerationItemResponse, status_code=201)
async def submit_report(
    body: ModerationItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.USER)),
):
    """User-submitted 'wrong score' report (FR-2.9) — never auto-applied."""
    repo = ModerationRepository(db)
    item = await repo.create(
        item_type=body.item_type,
        entity_type=body.entity_type,
        entity_id=body.entity_id,
        payload=json.dumps(body.payload, default=str) if body.payload else None,
        status="open",
        submitter_id=user.id,
    )
    return item


@router.get("", response_model=list[ModerationItemResponse])
async def list_moderation(
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(UserRole.ADMIN)),
):
    repo = ModerationRepository(db)
    return await repo.list_by_status(status)


@router.post("/{item_id}/review", response_model=ModerationItemResponse)
async def review_item(
    item_id: uuid.UUID,
    body: ModerationItemReview,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role(UserRole.ADMIN)),
):
    """Accept or dismiss a submitted report (moderator / competition manager)."""
    if body.status not in ("accepted", "dismissed"):
        raise HTTPException(status_code=422, detail="status must be 'accepted' or 'dismissed'")
    repo = ModerationRepository(db)
    item = await repo.get(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Moderation item not found")
    item.status = body.status
    item.reviewer_id = user.id
    item.reviewed_at = datetime.now(UTC)
    await db.flush()
    return item
