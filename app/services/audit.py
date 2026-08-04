"""Append-only audit trail for staff/admin mutations (FR-12.4).

Every create/edit/delete on match data is recorded with the actor identity,
timestamp, action, and a JSON diff of before/after state. Nothing is silently
overwritten.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance import AuditLog


async def record_audit(
    session: AsyncSession,
    entity_type: str,
    entity_id: uuid.UUID,
    action: str,
    actor_id: uuid.UUID | None = None,
    reason: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
) -> AuditLog | None:
    """Write an audit entry. Returns None when no actor is provided (system change)."""
    if actor_id is None:
        return None
    diff = None
    if before is not None or after is not None:
        diff = json.dumps({"before": before, "after": after}, default=str)
    entry = AuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        reason=reason,
        diff=diff,
        actor_id=actor_id,
    )
    session.add(entry)
    await session.flush()
    return entry
