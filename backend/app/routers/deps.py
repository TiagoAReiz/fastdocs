import hashlib
from typing import Callable

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.redis_client import rate_limit_check
from app.core.config import settings
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
    return request.app.state.checkpointer.saver


def _rate_limiter(endpoint_tag: str, limit: int, window: int) -> Callable:
    async def dependency(
        request: Request,
        response: Response,
        tenant: TenantContext = Depends(get_current_tenant),
    ) -> None:
        key = f"ratelimit:{tenant.tenant_id}:{endpoint_tag}"
        allowed, headers = await rate_limit_check(key, limit, window)
        for k, v in headers.items():
            response.headers[k] = v
        if not allowed:
            response.headers["Retry-After"] = str(window)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
                headers={**headers, "Retry-After": str(window)},
            )

    return dependency


rate_limit_ingest = _rate_limiter(
    "ingest", settings.RATE_LIMIT_INGEST, settings.RATE_LIMIT_INGEST_WINDOW
)
rate_limit_query = _rate_limiter(
    "query", settings.RATE_LIMIT_QUERY, settings.RATE_LIMIT_QUERY_WINDOW
)
