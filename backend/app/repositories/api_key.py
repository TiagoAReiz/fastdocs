from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


async def get_by_hash(db: AsyncSession, hash_key: str) -> ApiKey | None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.hash_key == hash_key, ApiKey.is_active.is_(True))
    )
    return result.scalar_one_or_none()


async def create(db: AsyncSession, id_tenant: UUID, hash_key: str, label: str | None = None) -> ApiKey:
    api_key = ApiKey(id_tenant=id_tenant, hash_key=hash_key, label=label)
    db.add(api_key)
    await db.flush()
    return api_key
