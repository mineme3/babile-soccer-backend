import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import AuditLog, ModerationItem
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AuditLog)

    async def list_for_entity(self, entity_type: str, entity_id: uuid.UUID, limit: int = 50) -> list[AuditLog]:
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 100) -> list[AuditLog]:
        stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ModerationRepository(BaseRepository[ModerationItem]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ModerationItem)

    async def list_by_status(self, status: str | None = None, limit: int = 50) -> list[ModerationItem]:
        stmt = select(ModerationItem)
        if status:
            stmt = stmt.where(ModerationItem.status == status)
        stmt = stmt.order_by(ModerationItem.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
