import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_list_competitions(client: AsyncClient, create_user):
    _, token = await create_user(role="admin")

    resp = await client.post(
        "/api/v1/competitions",
        json={
            "name": "Babile Premier League",
            "country": "Ethiopia",
            "level": "local",
            "format": "league",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    comp_id = resp.json()["id"]

    resp = await client.get("/api/v1/competitions")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert comp_id in ids


@pytest.mark.asyncio
async def test_create_competition_requires_staff_or_admin(client: AsyncClient):
    resp = await client.post(
        "/api/v1/competitions",
        json={
            "name": "Unauthorized League",
            "country": "Ethiopia",
            "level": "local",
            "format": "league",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_standings_endpoint(client: AsyncClient):
    resp = await client.get("/api/v1/competitions/00000000-0000-0000-0000-000000000000/standings")
    assert resp.status_code == 404
