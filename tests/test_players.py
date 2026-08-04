import pytest
from httpx import AsyncClient


async def _create_team(client: AsyncClient, token: str, name: str = "Babile FC") -> str:
    resp = await client.post(
        "/api/v1/teams",
        json={"name": name, "country": "Ethiopia"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _create_player(
    client: AsyncClient,
    token: str,
    team_id: str,
    jersey: int,
    name: str = "Player",
):
    return await client.post(
        "/api/v1/players",
        json={
            "team_id": team_id,
            "name": name,
            "jersey_number": jersey,
            "position": "forward",
        },
        headers={"Authorization": f"Bearer {token}"},
    )


@pytest.mark.asyncio
async def test_duplicate_jersey_on_same_team_rejected(client: AsyncClient, create_user):
    _, token = await create_user(role="admin")
    team_id = await _create_team(client, token)

    resp = await _create_player(client, token, team_id, 10, "Alice")
    assert resp.status_code == 201

    resp = await _create_player(client, token, team_id, 10, "Bob")
    assert resp.status_code == 409
    assert "Jersey number 10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_missing_jersey_on_same_team_allowed(client: AsyncClient, create_user):
    """Players without a jersey number don't conflict with each other."""
    _, token = await create_user(role="admin")
    team_id = await _create_team(client, token)

    for name in ("Alice", "Bob"):
        resp = await client.post(
            "/api/v1/players",
            json={"team_id": team_id, "name": name},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201


@pytest.mark.asyncio
async def test_same_jersey_on_different_teams_allowed(client: AsyncClient, create_user):
    _, token = await create_user(role="admin")
    team_a = await _create_team(client, token, "Team A")
    team_b = await _create_team(client, token, "Team B")

    assert (await _create_player(client, token, team_a, 10)).status_code == 201
    assert (await _create_player(client, token, team_b, 10)).status_code == 201


@pytest.mark.asyncio
async def test_update_to_taken_jersey_rejected(client: AsyncClient, create_user):
    _, token = await create_user(role="admin")
    team_id = await _create_team(client, token)

    assert (await _create_player(client, token, team_id, 10, "Alice")).status_code == 201
    p2 = (await _create_player(client, token, team_id, 7, "Bob")).json()

    resp = await client.patch(
        f"/api/v1/players/{p2['id']}",
        json={"jersey_number": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 409
    assert "Jersey number 10" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_update_keeping_own_jersey_allowed(client: AsyncClient, create_user):
    _, token = await create_user(role="admin")
    team_id = await _create_team(client, token)

    p1 = (await _create_player(client, token, team_id, 10, "Alice")).json()

    resp = await client.patch(
        f"/api/v1/players/{p1['id']}",
        json={"jersey_number": 10},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["jersey_number"] == 10
