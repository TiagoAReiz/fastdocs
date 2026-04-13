import hashlib
import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import HTTPException, status
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.redis_client import cache_get, cache_set
from app.models.chat_message import ChatMessage
from app.models.chat_thread import ChatThread
from app.repositories import chat_message as chat_message_repo
from app.repositories import chat_thread as chat_thread_repo
from app.schemas.chat import (
    ChatMessageResponse,
    MessageItem,
    MessageRole,
    Source,
    ThreadDetailResponse,
    ThreadListResponse,
    ThreadSummary,
)
from app.schemas.deps import TenantContext
from app.services.rag_graph import build_rag_graph

HISTORY_LIMIT = 10


def _cache_key(tenant_id: UUID, query: str) -> str:
    digest = hashlib.sha256(f"{tenant_id}{query}".encode()).hexdigest()
    return f"cache:query:{tenant_id}:{digest}"


def _to_lc_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    out: list[BaseMessage] = []
    for m in messages:
        if m.role == "user":
            out.append(HumanMessage(content=m.content))
        else:
            out.append(AIMessage(content=m.content))
    return out


async def _get_or_create_thread(
    db: AsyncSession,
    tenant: TenantContext,
    id_project: UUID,
    id_thread: UUID | None,
    first_message: str,
) -> ChatThread:
    if id_thread is None:
        return await chat_thread_repo.create(
            db, tenant.tenant_id, id_project, name=first_message[:60]
        )
    thread = await chat_thread_repo.get_by_id(db, id_thread, tenant.tenant_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return thread


async def send_message(
    db: AsyncSession,
    tenant: TenantContext,
    id_project: UUID,
    query: str,
    checkpointer: BaseCheckpointSaver,
    id_thread: UUID | None = None,
) -> ChatMessageResponse:
    thread = await _get_or_create_thread(db, tenant, id_project, id_thread, query)

    await chat_message_repo.create(
        db, thread.id, tenant.tenant_id, role="user", content=query
    )

    # Cache lookup
    key = _cache_key(tenant.tenant_id, query)
    cached = await cache_get(key)
    if cached is not None:
        answer = cached["answer"]
        sources = cached["sources"]
        await chat_message_repo.create(
            db, thread.id, tenant.tenant_id, role="agent", content=answer, sources=sources,
        )
        await chat_thread_repo.touch(db, thread)
        await db.commit()
        return ChatMessageResponse(
            message_agent=answer,
            id_thread=thread.id,
            sources=[Source(**s) for s in sources],
        )

    history = await chat_message_repo.list_by_thread(
        db, thread.id, tenant.tenant_id, limit=HISTORY_LIMIT
    )
    lc_history = _to_lc_messages(history)

    graph = build_rag_graph(db, checkpointer)
    final_state = await graph.ainvoke(
        {
            "id_tenant": tenant.tenant_id,
            "id_project": id_project,
            "id_thread": thread.id,
            "query": query,
            "messages": lc_history,
        },
        config={"configurable": {"thread_id": str(thread.id)}},
    )

    answer = final_state.get("answer", "")
    sources = final_state.get("sources", [])

    # Populate cache
    await cache_set(key, {"answer": answer, "sources": sources})

    await chat_message_repo.create(
        db,
        thread.id,
        tenant.tenant_id,
        role="agent",
        content=answer,
        sources=sources,
    )
    await chat_thread_repo.touch(db, thread)
    await db.commit()

    return ChatMessageResponse(
        message_agent=answer,
        id_thread=thread.id,
        sources=[Source(**s) for s in sources],
    )


async def send_message_stream(
    db: AsyncSession,
    tenant: TenantContext,
    id_project: UUID,
    query: str,
    checkpointer: BaseCheckpointSaver,
    id_thread: UUID | None = None,
) -> AsyncIterator[str]:
    thread = await _get_or_create_thread(db, tenant, id_project, id_thread, query)

    await chat_message_repo.create(
        db, thread.id, tenant.tenant_id, role="user", content=query
    )

    # Cache hit — return complete answer as single SSE event
    key = _cache_key(tenant.tenant_id, query)
    cached = await cache_get(key)
    if cached is not None:
        answer = cached["answer"]
        sources = cached["sources"]
        await chat_message_repo.create(
            db, thread.id, tenant.tenant_id, role="agent", content=answer, sources=sources,
        )
        await chat_thread_repo.touch(db, thread)
        await db.commit()
        yield f"data: {json.dumps({'chunk': answer})}\n\n"
        yield f"data: {json.dumps({'done': True, 'id_thread': str(thread.id), 'sources': sources})}\n\n"
        return

    history = await chat_message_repo.list_by_thread(
        db, thread.id, tenant.tenant_id, limit=HISTORY_LIMIT
    )
    lc_history = _to_lc_messages(history)

    graph = build_rag_graph(db, checkpointer)

    accumulated = ""
    final_sources: list[dict] = []

    async for mode, payload in graph.astream(
        {
            "id_tenant": tenant.tenant_id,
            "id_project": id_project,
            "id_thread": thread.id,
            "query": query,
            "messages": lc_history,
        },
        config={"configurable": {"thread_id": str(thread.id)}},
        stream_mode=["messages", "updates"],
    ):
        if mode == "messages":
            chunk, _meta = payload
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                accumulated += text
                yield f"data: {json.dumps({'chunk': text})}\n\n"
        elif mode == "updates":
            for node_update in payload.values():
                if "sources" in node_update and node_update["sources"]:
                    final_sources = node_update["sources"]

    # Populate cache
    await cache_set(key, {"answer": accumulated, "sources": final_sources})

    yield f"data: {json.dumps({'done': True, 'id_thread': str(thread.id), 'sources': final_sources})}\n\n"

    await chat_message_repo.create(
        db,
        thread.id,
        tenant.tenant_id,
        role="agent",
        content=accumulated,
        sources=final_sources,
    )
    await chat_thread_repo.touch(db, thread)
    await db.commit()


async def list_threads(
    db: AsyncSession,
    tenant: TenantContext,
    id_project: UUID,
    page: int,
    page_size: int,
) -> ThreadListResponse:
    threads, _total = await chat_thread_repo.list_by_project(
        db, tenant.tenant_id, id_project, page, page_size
    )
    return ThreadListResponse(
        threads=[
            ThreadSummary(id=t.id, name=t.name, created_at=t.created_at) for t in threads
        ]
    )


async def get_thread(
    db: AsyncSession, tenant: TenantContext, id_thread: UUID
) -> ThreadDetailResponse:
    thread = await chat_thread_repo.get_by_id(db, id_thread, tenant.tenant_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    messages = await chat_message_repo.list_by_thread(db, thread.id, tenant.tenant_id)
    return ThreadDetailResponse(
        id=thread.id,
        name=thread.name,
        messages=[
            MessageItem(
                id=m.id,
                role=MessageRole(m.role),
                message=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )
