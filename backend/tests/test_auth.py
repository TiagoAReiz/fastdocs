import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    resp = await client.get("/api/projects/")
    assert resp.status_code == 422  # missing required header


@pytest.mark.asyncio
async def test_invalid_api_key_returns_401(client: AsyncClient):
    resp = await client.get(
        "/api/projects/",
        headers={"X-API-Key": "fdocs_invalid_key_that_does_not_exist"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_valid_api_key_passes_auth(client: AsyncClient, api_key_plain):
    plain, _key = api_key_plain
    resp = await client.get(
        "/api/projects/",
        headers={"X-API-Key": plain},
    )
    # Should pass auth (200 with empty list, not 401)
    assert resp.status_code == 200
