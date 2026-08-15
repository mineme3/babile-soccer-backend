"""Real-time broadcast via Server-Sent Events over Redis pub/sub.

Broadcast failures never break the request that triggered them, so data entry
keeps working even under a poor network connection.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

KEEP_ALIVE_SECONDS = 15.0


class SSEService:
    CHANNEL_MATCH_EVENTS = "match:events"
    CHANNEL_STANDINGS = "standings:updates"
    CHANNEL_DATA_CHANGES = "data:changes"
    CHANNEL_NEWS = "news:published"

    def __init__(self):
        self._redis: aioredis.Redis | None = None

    def get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def publish(self, channel: str, data: dict) -> None:
        try:
            r = self.get_redis()
            await r.publish(channel, json.dumps(data, default=str))
        except Exception:
            logger.warning("Failed to publish to channel %s (real-time broadcast unavailable)", channel)

    async def broadcast_change(self, resource: str, action: str, entity_id: str) -> None:
        """Announce that a catalog entity was created/updated so clients refresh it."""
        await self.publish(
            self.CHANNEL_DATA_CHANGES,
            {"type": "data_change", "resource": resource, "action": action, "id": entity_id},
        )

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        async for kind, payload in self._filtered(channel, None, None):
            yield self._format(kind, payload, "message")

    async def match_event_stream(self, match_id: str | None = None) -> AsyncGenerator[str, None]:
        async for kind, payload in self._filtered(self.CHANNEL_MATCH_EVENTS, match_id, "match_id"):
            yield self._format(kind, payload, "match_event")

    async def data_change_stream(self) -> AsyncGenerator[str, None]:
        async for kind, payload in self._filtered(self.CHANNEL_DATA_CHANGES, None, None):
            yield self._format(kind, payload, "data_change")

    async def standings_stream(self, competition_id: str | None = None) -> AsyncGenerator[str, None]:
        async for kind, payload in self._filtered(self.CHANNEL_STANDINGS, competition_id, "competition_id"):
            yield self._format(kind, payload, "standings")

    async def news_stream(self) -> AsyncGenerator[str, None]:
        async for kind, payload in self._filtered(self.CHANNEL_NEWS, None, None):
            yield self._format(kind, payload, "news")

    @staticmethod
    def _format(kind: str, payload: str, event_name: str) -> str:
        if kind == "keepalive":
            return ": keep-alive\n\n"
        return f"event: {event_name}\ndata: {payload}\n\n"

    async def _filtered(
        self,
        channel: str,
        filter_id: str | None,
        filter_key: str | None,
    ) -> AsyncGenerator[tuple[str, str], None]:
        r = self.get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)
        try:
            while True:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=KEEP_ALIVE_SECONDS
                    )
                except Exception:
                    message = None
                if message is None:
                    yield "keepalive", ""
                    continue
                if message["type"] != "message":
                    continue
                data = message["data"]
                if filter_id and filter_key:
                    try:
                        if json.loads(data).get(filter_key) != filter_id:
                            continue
                    except json.JSONDecodeError:
                        continue
                yield "data", data
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.close()
            except Exception:
                pass


sse_service = SSEService()
