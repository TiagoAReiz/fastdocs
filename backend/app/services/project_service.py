from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.repositories import project as project_repo
from app.schemas.deps import TenantContext
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)


def _to_response(project: Project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        name=project.name,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


async def create(
    db: AsyncSession, tenant: TenantContext, body: ProjectCreate
) -> ProjectResponse:
    project = await project_repo.create(db, tenant.tenant_id, body.name)
    await db.commit()
    return _to_response(project)


async def list_projects(
    db: AsyncSession, tenant: TenantContext, page: int, page_size: int
) -> ProjectListResponse:
    items, total = await project_repo.list_by_tenant(db, tenant.tenant_id, page, page_size)
    return ProjectListResponse(
        projects=[_to_response(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _get_or_404(db: AsyncSession, tenant: TenantContext, id: UUID) -> Project:
    project = await project_repo.get_by_id(db, id, tenant.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def get(db: AsyncSession, tenant: TenantContext, id: UUID) -> ProjectResponse:
    return _to_response(await _get_or_404(db, tenant, id))


async def update(
    db: AsyncSession, tenant: TenantContext, id: UUID, body: ProjectUpdate
) -> ProjectResponse:
    project = await _get_or_404(db, tenant, id)
    await project_repo.update(db, project, **body.model_dump(exclude_unset=True))
    await db.commit()
    await db.refresh(project)
    return _to_response(project)


async def delete(db: AsyncSession, tenant: TenantContext, id: UUID) -> None:
    project = await _get_or_404(db, tenant, id)
    await project_repo.soft_delete(db, project)
    await db.commit()
