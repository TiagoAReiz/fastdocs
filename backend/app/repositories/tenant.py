from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


async def get_by_id(db: AsyncSession, id: UUID) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.id == id, Tenant.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def get_by_name(db: AsyncSession, name: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.name == name, Tenant.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, name: str, gemini_api_key_encrypted: str) -> Tenant:
    tenant = Tenant(name=name, gemini_api_key_encrypted=gemini_api_key_encrypted)
    db.add(tenant)
    await db.flush()
    return tenant


async def update(db: AsyncSession, tenant: Tenant, **fields: object) -> Tenant:
    for key, value in fields.items():
        setattr(tenant, key, value)
    await db.flush()
    return tenant


async def soft_delete(db: AsyncSession, tenant: Tenant) -> None:
    from datetime import datetime, timezone
    tenant.deleted_at = datetime.now(timezone.utc)
    await db.flush()


async def list_paginated(
    db: AsyncSession, page: int, page_size: int
) -> tuple[list[Tenant], int]:
    offset = (page - 1) * page_size
    count_result = await db.execute(
        select(func.count()).select_from(Tenant).where(Tenant.deleted_at.is_(None))
    )
    total = count_result.scalar_one()
    result = await db.execute(
        select(Tenant)
        .where(Tenant.deleted_at.is_(None))
        .order_by(Tenant.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    return list(result.scalars().all()), total
