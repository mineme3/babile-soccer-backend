import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_matches(client: AsyncClient):
    resp = await client.get("/api/v1/matches")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_live_matches(client: AsyncClient):
    resp = await client.get("/api/v1/matches/live")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_match_not_found(client: AsyncClient):
    resp = await client.get("/api/v1/matches/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
