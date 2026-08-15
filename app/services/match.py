"""Match lifecycle management.

Staff and admin drive every match from the admin website or the offline-first
operator console. The mobile app polls REST endpoints for updates.

The match minute is *client-authoritative*: the operator device runs a ticker
and syncs the current minute to the server (`sync_minute`), which stores it.
This keeps the console fully usable offline.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.match import (
    EventPeriod,
    EventType,
    LineupEntry,
    Match,
    MatchEvent,
    MatchPeriod,
    MatchStatus,
    RecordStatus,
)
from app.repositories.match import LineupEntryRepository, MatchEventRepository, MatchRepository
from app.services.audit import record_audit

SCORE_EVENT_TYPES = (
    EventType.GOAL,
    EventType.OWN_GOAL,
    EventType.PENALTY_SCORED,
)

_PERIOD_OF_PERIOD_ENUM = {
    MatchPeriod.FIRST_HALF: EventPeriod.FIRST_HALF,
    MatchPeriod.SECOND_HALF: EventPeriod.SECOND_HALF,
    MatchPeriod.EXTRA_TIME: EventPeriod.EXTRA_TIME,
    MatchPeriod.PENALTIES: EventPeriod.PENALTIES,
    MatchPeriod.HALF_TIME: EventPeriod.FIRST_HALF,
    MatchPeriod.FULL_TIME: EventPeriod.SECOND_HALF,
    MatchPeriod.NOT_STARTED: EventPeriod.FIRST_HALF,
}


class MatchService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.match_repo = MatchRepository(session)
        self.event_repo = MatchEventRepository(session)
        self.lineup_repo = LineupEntryRepository(session)

    # ── Creation / deletion ─────────────────────────────────

    async def create_match(self, actor_id: uuid.UUID, **kwargs) -> Match:
        """Create a match with duplicate-fixture detection (Section 6.4)."""
        existing = await self._find_duplicate(
            stage_id=kwargs.get("stage_id"),
            group_id=kwargs.get("group_id"),
            home_team_id=kwargs.get("home_team_id"),
            away_team_id=kwargs.get("away_team_id"),
            kickoff_at=kwargs.get("kickoff_at"),
        )
        if existing:
            raise ValueError("Duplicate fixture: these two teams already have a match at that time")
        match = await self.match_repo.create(**kwargs)
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match.id,
            action="create",
            actor_id=actor_id,
            after={"home_team_id": str(match.home_team_id), "away_team_id": str(match.away_team_id)},
        )
        return match

    async def delete_match(self, match_id: uuid.UUID, actor_id: uuid.UUID) -> bool:
        match = await self._require_match(match_id)
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="delete",
            actor_id=actor_id,
            after={
                "home_team_id": str(match.home_team_id),
                "away_team_id": str(match.away_team_id),
                "status": match.status.value,
            },
        )
        return await self.match_repo.delete(match_id)

    # ── Lifecycle ───────────────────────────────────────────

    async def start_match(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None, announcement: str | None = None) -> Match:
        match = await self._set_status(
            match_id,
            status=MatchStatus.LIVE,
            period=MatchPeriod.FIRST_HALF,
            minute=1,
        )
        if announcement:
            await record_audit(
                self.session,
                entity_type="match",
                entity_id=match_id,
                action="announcement",
                actor_id=actor_id,
                after={"announcement": announcement},
            )
        await self._ensure_record_status(match, RecordStatus.SUBMITTED, actor_id)
        return match

    async def set_half_time(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.HALF_TIME,
            period=MatchPeriod.HALF_TIME,
            actor_id=actor_id,
        )

    async def set_second_half(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.LIVE,
            period=MatchPeriod.SECOND_HALF,
            actor_id=actor_id,
        )

    async def set_extra_time(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.EXTRA_TIME,
            period=MatchPeriod.EXTRA_TIME,
            actor_id=actor_id,
        )

    async def set_penalties(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.PENALTIES,
            period=MatchPeriod.PENALTIES,
            actor_id=actor_id,
        )

    async def set_full_time(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        match = await self._set_status(
            match_id,
            status=MatchStatus.FULL_TIME,
            period=MatchPeriod.FULL_TIME,
            actor_id=actor_id,
        )
        if match.record_status not in (RecordStatus.PUBLISHED, RecordStatus.CORRECTED):
            match.record_status = RecordStatus.PUBLISHED
            await self.session.flush()
            await record_audit(
                self.session,
                entity_type="match",
                entity_id=match_id,
                action="publish",
                actor_id=actor_id,
            )
        return match

    async def set_postponed(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.POSTPONED,
            period=MatchPeriod.NOT_STARTED,
            actor_id=actor_id,
        )

    async def set_cancelled(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.CANCELLED,
            period=MatchPeriod.NOT_STARTED,
            actor_id=actor_id,
        )

    async def set_abandoned(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        return await self._set_status(
            match_id,
            status=MatchStatus.ABANDONED,
            period=MatchPeriod.NOT_STARTED,
            actor_id=actor_id,
        )

    async def set_walkover(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        match = await self._set_status(
            match_id,
            status=MatchStatus.WALKOVER,
            period=MatchPeriod.FULL_TIME,
            actor_id=actor_id,
        )
        return match

    # ── Minute / hydration (client-authoritative ticker) ────

    async def sync_minute(
        self,
        match_id: uuid.UUID,
        minute: int,
        period: MatchPeriod | None = None,
    ) -> Match:
        """The operator console's ticker reports the current minute/period."""
        match = await self._require_match(match_id)
        match.current_minute = max(0, min(int(minute), 210))
        if period is not None:
            match.current_period = period
        await self.session.flush()
        return match

    async def set_hydration_break(
        self,
        match_id: uuid.UUID,
        active: bool,
        actor_id: uuid.UUID | None = None,
    ) -> Match:
        """Start/stop a hydration break — the ticker is paused meanwhile."""
        match = await self._require_match(match_id)
        match.hydration_break_at = datetime.now(UTC) if active else None
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="hydration_break" if active else "hydration_resume",
            actor_id=actor_id,
        )
        return match

    async def add_time(
        self,
        match_id: uuid.UUID,
        minutes: int,
        actor_id: uuid.UUID | None = None,
    ) -> Match:
        """Add stoppage time to the current half."""
        match = await self._require_match(match_id)
        match.added_time = max(0, min(int(minutes), 10))
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="add_time",
            actor_id=actor_id,
            detail=f"Added {match.added_time} minutes",
        )
        return match

    # ── Results ─────────────────────────────────────────────

    async def submit_result_only(
        self,
        match_id: uuid.UUID,
        home_score: int,
        away_score: int,
        scorers: list[dict] | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Match:
        """Tier-3 fallback (6.3-E): final score + scorers, no live timeline."""
        match = await self._require_match(match_id)
        match.home_score = home_score
        match.away_score = away_score
        match.status = MatchStatus.FULL_TIME
        match.current_period = MatchPeriod.FULL_TIME
        match.is_result_only = True
        match.is_live_tracked = False
        match.record_status = RecordStatus.PUBLISHED

        if scorers:
            for i, s in enumerate(scorers):
                await self.event_repo.create(
                    match_id=match_id,
                    event_type=EventType(s["event_type"]),
                    minute=s.get("minute", 0),
                    team_id=uuid.UUID(s["team_id"]),
                    player_id=uuid.UUID(s["player_id"]) if s.get("player_id") else None,
                    sequence=i + 1,
                    period=self._period_for(match),
                )

        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="result_only",
            actor_id=actor_id,
            after={"home_score": home_score, "away_score": away_score},
        )
        return match

    # ── Lineups ─────────────────────────────────────────────

    async def submit_lineup(
        self,
        match_id: uuid.UUID,
        team_id: uuid.UUID,
        player_ids: list[uuid.UUID],
        is_starting_xi: bool = True,
    ) -> list[LineupEntry]:
        await self._require_match(match_id)
        await self.session.execute(
            delete(LineupEntry).where(
                LineupEntry.match_id == match_id,
                LineupEntry.team_id == team_id,
            )
        )
        entries = []
        for i, player_id in enumerate(player_ids):
            entry = await self.lineup_repo.create(
                match_id=match_id,
                team_id=team_id,
                player_id=player_id,
                is_starting_xi=is_starting_xi,
                formation_place=i + 1,
            )
            entries.append(entry)
        await self.session.flush()
        return entries

    # ── Events ──────────────────────────────────────────────

    async def record_event(
        self,
        match_id: uuid.UUID,
        event_type: EventType,
        minute: int,
        team_id: uuid.UUID,
        player_id: uuid.UUID | None = None,
        assist_player_id: uuid.UUID | None = None,
        player_off_id: uuid.UUID | None = None,
        player_on_id: uuid.UUID | None = None,
        detail: str | None = None,
        period: EventPeriod | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> MatchEvent:
        match = await self._require_match(match_id)

        await self._validate_event(match, event_type, team_id, player_id)

        if event_type in SCORE_EVENT_TYPES:
            if team_id == match.home_team_id:
                match.home_score += 1
            elif team_id == match.away_team_id:
                match.away_score += 1

        # Post-publish edits must be audit-logged, never silently overwritten.
        if match.record_status in (RecordStatus.PUBLISHED, RecordStatus.CORRECTED):
            match.record_status = RecordStatus.CORRECTED
            await record_audit(
                self.session,
                entity_type="match",
                entity_id=match_id,
                action="correct_event",
                actor_id=actor_id,
                after={"event_type": event_type.value, "minute": minute},
            )

        sequence = await self._next_event_sequence(match_id)
        event = await self.event_repo.create(
            match_id=match_id,
            event_type=event_type,
            minute=minute,
            team_id=team_id,
            player_id=player_id,
            assist_player_id=assist_player_id,
            player_off_id=player_off_id,
            player_on_id=player_on_id,
            detail=detail,
            sequence=sequence,
            period=period or self._period_for(match),
        )

        await self.session.flush()
        await self.session.refresh(event)
        return event

    async def sync_events(
        self,
        match_id: uuid.UUID,
        events: list[dict],
        actor_id: uuid.UUID | None = None,
    ) -> list[MatchEvent]:
        """Process offline-queued events in order (poor-network fallback)."""
        created = []
        for ev in events:
            event = await self.record_event(
                match_id=match_id,
                event_type=EventType(ev["event_type"]),
                minute=ev["minute"],
                team_id=uuid.UUID(ev["team_id"]),
                player_id=uuid.UUID(ev["player_id"]) if ev.get("player_id") else None,
                assist_player_id=(
                    uuid.UUID(ev["assist_player_id"]) if ev.get("assist_player_id") else None
                ),
                player_off_id=(
                    uuid.UUID(ev["player_off_id"]) if ev.get("player_off_id") else None
                ),
                player_on_id=(
                    uuid.UUID(ev["player_on_id"]) if ev.get("player_on_id") else None
                ),
                detail=ev.get("detail"),
                actor_id=actor_id,
            )
            created.append(event)
        return created

    # ── Statistics ──────────────────────────────────────────

    async def set_statistics(self, match_id: uuid.UUID, team_id: uuid.UUID, stats: dict) -> list:
        """Upsert per-team match statistics (possession, shots, corners, fouls…)."""
        await self._require_match(match_id)
        from app.models.match import MatchStatistic

        await self.session.execute(
            delete(MatchStatistic).where(
                MatchStatistic.match_id == match_id,
                MatchStatistic.team_id == team_id,
            )
        )
        rows = []
        for name, value in (stats or {}).items():
            row = MatchStatistic(
                match_id=match_id,
                team_id=team_id,
                stat_name=name,
                stat_value=str(value),
            )
            self.session.add(row)
            rows.append(row)
        await self.session.flush()
        return rows

    async def get_statistics(self, match_id: uuid.UUID) -> dict[uuid.UUID, dict[str, str]]:
        from app.models.match import MatchStatistic

        stmt = select(MatchStatistic).where(MatchStatistic.match_id == match_id)
        result = await self.session.execute(stmt)
        grouped: dict[uuid.UUID, dict[str, str]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.team_id, {})[row.stat_name] = row.stat_value
        return grouped

    # ── Disputes (dual-entry conflict, 6.3-D) ───────────────

    async def dispute_match(self, match_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> Match:
        match = await self._require_match(match_id)
        match.is_disputed = True
        match.record_status = RecordStatus.DISPUTED
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="dispute",
            actor_id=actor_id,
        )
        return match

    async def resolve_dispute(
        self,
        match_id: uuid.UUID,
        home_score: int,
        away_score: int,
        actor_id: uuid.UUID | None = None,
    ) -> Match:
        match = await self._require_match(match_id)
        match.home_score = home_score
        match.away_score = away_score
        match.is_disputed = False
        match.record_status = RecordStatus.PUBLISHED
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="resolve_dispute",
            actor_id=actor_id,
            after={"home_score": home_score, "away_score": away_score},
        )
        return match

    # ── Helpers ─────────────────────────────────────────────

    async def _validate_event(
        self,
        match: Match,
        event_type: EventType,
        team_id: uuid.UUID,
        player_id: uuid.UUID | None,
    ) -> None:
        """Structural validation (Section 6.4): team ownership + player membership."""
        if team_id not in (match.home_team_id, match.away_team_id):
            raise ValueError("Team does not belong to this match")

        if player_id is None:
            return
        # A sub has two players (off/on); the primary player must belong to the team.
        await self._ensure_player_in_team(team_id, player_id)

    async def _ensure_player_in_team(self, team_id: uuid.UUID, player_id: uuid.UUID) -> None:
        from app.models.player import Player

        stmt = select(Player).where(
            Player.id == player_id,
            Player.team_id == team_id,
        )
        result = await self.session.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ValueError("Player does not belong to that team")

    async def _find_duplicate(
        self,
        stage_id: uuid.UUID,
        group_id: uuid.UUID | None,
        home_team_id: uuid.UUID,
        away_team_id: uuid.UUID,
        kickoff_at: datetime,
    ) -> Match | None:
        kickoff_date = kickoff_at.date() if hasattr(kickoff_at, "date") else kickoff_at
        if isinstance(kickoff_at, datetime):
            kickoff_date = kickoff_at.date()
        day_start = datetime.combine(kickoff_date, datetime.min.time(), tzinfo=UTC)
        day_end = datetime.combine(kickoff_date, datetime.max.time(), tzinfo=UTC)
        stmt = select(Match).where(
            Match.stage_id == stage_id,
            Match.home_team_id == home_team_id,
            Match.away_team_id == away_team_id,
            Match.kickoff_at >= day_start,
            Match.kickoff_at <= day_end,
        )
        if group_id:
            stmt = stmt.where(Match.group_id == group_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _period_for(self, match: Match) -> EventPeriod:
        return _PERIOD_OF_PERIOD_ENUM.get(match.current_period, EventPeriod.FIRST_HALF)

    async def _set_status(
        self,
        match_id: uuid.UUID,
        status: MatchStatus,
        period: MatchPeriod,
        minute: int | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> Match:
        match = await self._require_match(match_id)
        
        # Prevent restarting a completed match
        finished_statuses = {
            MatchStatus.FULL_TIME,
            MatchStatus.CANCELLED,
            MatchStatus.ABANDONED,
            MatchStatus.WALKOVER,
            MatchStatus.POSTPONED,
        }
        if status == MatchStatus.LIVE and match.status in finished_statuses:
            raise ValueError(
                f"Cannot start a match that is already {match.status.value}. "
                "Create a new match instead."
            )
        
        before_status = match.status.value
        match.status = status
        match.current_period = period
        if minute is not None:
            match.current_minute = minute
        await self.session.flush()
        await record_audit(
            self.session,
            entity_type="match",
            entity_id=match_id,
            action="status_change",
            actor_id=actor_id,
            before={"status": before_status},
            after={"status": status.value, "period": period.value},
        )
        return match

    async def _ensure_record_status(self, match: Match, status: RecordStatus, actor_id: uuid.UUID | None) -> None:
        if match.record_status != status:
            match.record_status = status
            await self.session.flush()
            await record_audit(
                self.session,
                entity_type="match",
                entity_id=match.id,
                action="record_status",
                actor_id=actor_id,
                after={"record_status": status.value},
            )

    async def _require_match(self, match_id: uuid.UUID) -> Match:
        match = await self.match_repo.get_with_enrich(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")
        return match

    async def _next_event_sequence(self, match_id: uuid.UUID) -> int:
        from sqlalchemy import func

        from app.models.match import MatchEvent as EventModel

        stmt = select(func.count()).select_from(EventModel).where(EventModel.match_id == match_id)
        result = await self.session.execute(stmt)
        return (result.scalar() or 0) + 1
