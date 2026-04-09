import hashlib

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.repositories import api_key as api_key_repo
from app.schemas.deps import TenantContext


async def get_current_tenant(
    x_api_key: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> TenantContext:
    hash_key = hashlib.sha256(x_api_key.encode()).hexdigest()
    api_key = await api_key_repo.get_by_hash(db, hash_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )
    return TenantContext(tenant_id=api_key.id_tenant, api_key_id=api_key.id)


def get_checkpointer(request: Request):
    return request.app.state.checkpointer
