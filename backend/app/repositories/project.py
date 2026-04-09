from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project


async def get_by_id(db: AsyncSession, id: UUID, tenant_id: UUID) -> Project | None:
    result = await db.execute(
        select(Project).where(Project.id == id, Project.id_tenant == tenant_id, Project.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_by_tenant(
    db: AsyncSession, tenant_id: UUID, page: int, page_size: int
) -> tuple[list[Project], int]:
    base = select(Project).where(Project.id_tenant == tenant_id, Project.deleted_at.is_(None))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create(db: AsyncSession, tenant_id: UUID, name: str) -> Project:
    project = Project(id_tenant=tenant_id, name=name)
    db.add(project)
    await db.flush()
    return project


async def update(db: AsyncSession, project: Project, **fields) -> Project:
    for key, value in fields.items():
        if hasattr(project, key):
            setattr(project, key, value)
    await db.flush()
    return project


async def soft_delete(db: AsyncSession, project: Project) -> None:
    project.deleted_at = func.now()
    await db.flush()
