import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_thread import ChatThread
from app.models.project import Project
from app.repositories import chat_message as chat_message_repo
from app.repositories import chat_thread as chat_thread_repo


@pytest.mark.asyncio
async def test_list_threads_empty(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
):
    resp = await client.get(
        "/api/chat/history",
        headers=auth_headers,
        params={"id_project": str(project.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["threads"] == []


@pytest.mark.asyncio
async def test_list_threads_with_thread(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    chat_thread: ChatThread,
):
    resp = await client.get(
        "/api/chat/history",
        headers=auth_headers,
        params={"id_project": str(project.id)},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["threads"]) >= 1
    assert any(t["id"] == str(chat_thread.id) for t in data["threads"])


@pytest.mark.asyncio
async def test_get_thread_detail(
    client: AsyncClient,
    auth_headers: dict,
    db: AsyncSession,
    project: Project,
    chat_thread: ChatThread,
    tenant,
):
    await chat_message_repo.create(
        db, chat_thread.id, tenant.id, role="user", content="hello"
    )
    await chat_message_repo.create(
        db, chat_thread.id, tenant.id, role="agent", content="hi there"
    )
    await db.commit()

    resp = await client.get(
        f"/api/chat/history/{chat_thread.id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(chat_thread.id)
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "agent"


@pytest.mark.asyncio
async def test_get_nonexistent_thread_404(
    client: AsyncClient,
    auth_headers: dict,
):
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/chat/history/{fake_id}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_send_message_cache_hit(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    mock_rate_limit,
    mock_redis_cache: dict,
):
    # Pre-populate cache with a response for any query
    # The cache key depends on tenant_id + query, so we mock cache_get to return a hit
    from unittest.mock import AsyncMock, patch

    cached_response = {
        "answer": "cached answer",
        "sources": [],
    }

    async def _cache_get_hit(key):
        return cached_response

    async def _cache_set_noop(key, value, ttl=None):
        pass

    with (
        patch("app.services.chat_service.cache_get", side_effect=_cache_get_hit),
        patch("app.services.chat_service.cache_set", side_effect=_cache_set_noop),
    ):
        resp = await client.post(
            "/api/chat/message",
            headers=auth_headers,
            json={
                "message": "test query",
                "id_project": str(project.id),
                "stream": False,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["message_agent"] == "cached answer"
    assert "id_thread" in data
