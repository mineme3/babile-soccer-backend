import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_and_login(client: AsyncClient):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "display_name": "Test User",
        "password": "password123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert data["role"] == "user"

    resp = await client.post("/api/v1/auth/login", json={
        "email": "test@example.com",
        "password": "password123",
    })
    assert resp.status_code == 200
    tokens = resp.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "me@example.com",
        "display_name": "Me",
        "password": "password123",
    })
    resp = await client.post("/api/v1/auth/login", json={
        "email": "me@example.com",
        "password": "password123",
    })
    token = resp.json()["access_token"]

    resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@example.com"
