from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.deps import require_admin
from app.schemas.admin import (
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyResponse,
    TenantCreate,
    TenantCreateResponse,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)
from app.schemas.deps import PaginationParams
from app.services import admin_service

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)],
)


@router.post("/tenants", response_model=TenantCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.create_tenant(db, body)


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    pagination: PaginationParams = Depends(),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_tenants(db, pagination.page, pagination.page_size)


@router.get("/tenants/{id}", response_model=TenantResponse)
async def get_tenant(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.get_tenant(db, id)


@router.patch("/tenants/{id}", response_model=TenantResponse)
async def update_tenant(
    id: UUID,
    body: TenantUpdate,
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.update_tenant(db, id, body)


@router.delete("/tenants/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await admin_service.delete_tenant(db, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/tenants/{id}/api-keys",
    response_model=ApiKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def emit_api_key(
    id: UUID,
    body: ApiKeyCreate = ApiKeyCreate(),
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.emit_api_key(db, id, body.label)


@router.get("/tenants/{id}/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    return await admin_service.list_api_keys(db, id)


@router.delete("/api-keys/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    id: UUID,
    db: AsyncSession = Depends(get_db),
):
    await admin_service.revoke_api_key(db, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
