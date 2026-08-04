from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.services.sse import sse_service

router = APIRouter(prefix="/api/v1/events", tags=["SSE"])


def _sse_stream(stream):
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/matches")
async def match_events(match_id: str | None = Query(None)):
    return _sse_stream(sse_service.match_event_stream(match_id))


@router.get("/standings")
async def standings_events(competition_id: str | None = Query(None)):
    return _sse_stream(sse_service.standings_stream(competition_id))


@router.get("/data")
async def data_change_events():
    """Broadcast whenever admin/staff create or update catalog data."""
    return _sse_stream(sse_service.data_change_stream())


@router.get("/news")
async def news_events():
    return _sse_stream(sse_service.news_stream())
