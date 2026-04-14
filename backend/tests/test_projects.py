import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers: dict):
    resp = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={"name": "My Project"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_projects_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/projects/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["projects"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_projects_pagination(client: AsyncClient, auth_headers: dict):
    for i in range(3):
        await client.post(
            "/api/projects/",
            headers=auth_headers,
            json={"name": f"Project {i}"},
        )

    resp = await client.get(
        "/api/projects/",
        headers=auth_headers,
        params={"page": 1, "page_size": 2},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["projects"]) == 2


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={"name": "Get Me"},
    )
    project_id = create_resp.json()["id"]

    resp = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Me"


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={"name": "Old Name"},
    )
    project_id = create_resp.json()["id"]

    resp = await client.put(
        f"/api/projects/{project_id}",
        headers=auth_headers,
        json={"name": "New Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "New Name"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={"name": "Delete Me"},
    )
    project_id = create_resp.json()["id"]

    resp = await client.delete(f"/api/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/projects/{project_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_project_404(client: AsyncClient, auth_headers: dict):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/projects/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404
