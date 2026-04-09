from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.deps import get_current_tenant
from app.schemas.deps import PaginationParams, TenantContext
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services import project_service

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.create(db, tenant, body)


@router.get("/", response_model=ProjectListResponse)
async def list_projects(
    pagination: PaginationParams = Depends(),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.list_projects(
        db, tenant, pagination.page, pagination.page_size
    )


@router.get("/{id}", response_model=ProjectResponse)
async def get_project(
    id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.get(db, tenant, id)


@router.put("/{id}", response_model=ProjectResponse)
async def update_project(
    id: UUID,
    body: ProjectUpdate,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await project_service.update(db, tenant, id, body)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await project_service.delete(db, tenant, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
