from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage


async def create(
    db: AsyncSession,
    id_thread: UUID,
    id_tenant: UUID,
    role: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
) -> ChatMessage:
    message = ChatMessage(
        id_thread=id_thread,
        id_tenant=id_tenant,
        role=role,
        content=content,
        sources=sources,
    )
    db.add(message)
    await db.flush()
    return message


async def list_by_thread(
    db: AsyncSession,
    id_thread: UUID,
    tenant_id: UUID,
    limit: int | None = None,
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.id_thread == id_thread, ChatMessage.id_tenant == tenant_id)
        .order_by(ChatMessage.created_at.asc())
    )
    if limit is not None:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.id_thread == id_thread, ChatMessage.id_tenant == tenant_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        return list(reversed(list(result.scalars().all())))

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_by_thread(db: AsyncSession, id_thread: UUID, tenant_id: UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.id_thread == id_thread, ChatMessage.id_tenant == tenant_id)
    )
    return result.scalar_one()
