from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_thread import ChatThread


async def create(
    db: AsyncSession,
    id_tenant: UUID,
    id_project: UUID,
    name: str,
) -> ChatThread:
    thread = ChatThread(id_tenant=id_tenant, id_project=id_project, name=name)
    db.add(thread)
    await db.flush()
    return thread


async def get_by_id(db: AsyncSession, id: UUID, tenant_id: UUID) -> ChatThread | None:
    result = await db.execute(
        select(ChatThread).where(
            ChatThread.id == id,
            ChatThread.id_tenant == tenant_id,
            ChatThread.deleted_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def list_by_project(
    db: AsyncSession,
    tenant_id: UUID,
    id_project: UUID,
    page: int,
    page_size: int,
) -> tuple[list[ChatThread], int]:
    base = select(ChatThread).where(
        ChatThread.id_tenant == tenant_id,
        ChatThread.id_project == id_project,
        ChatThread.deleted_at.is_(None),
    )

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base.order_by(ChatThread.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def touch(db: AsyncSession, thread: ChatThread) -> None:
    thread.updated_at = func.now()
    await db.flush()


async def soft_delete(db: AsyncSession, thread: ChatThread) -> None:
    thread.deleted_at = func.now()
    await db.flush()
