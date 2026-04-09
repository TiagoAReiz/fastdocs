from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant


async def get_by_id(db: AsyncSession, id: UUID) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.id == id, Tenant.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def get_by_name(db: AsyncSession, name: str) -> Tenant | None:
    result = await db.execute(select(Tenant).where(Tenant.name == name, Tenant.deleted_at.is_(None)))
    return result.scalar_one_or_none()


async def create(db: AsyncSession, name: str) -> Tenant:
    tenant = Tenant(name=name)
    db.add(tenant)
    await db.flush()
    return tenant
