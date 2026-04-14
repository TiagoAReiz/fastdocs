from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document


async def get_by_id(db: AsyncSession, id: UUID, tenant_id: UUID) -> Document | None:
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.metadata_rel))
        .where(Document.id == id, Document.id_tenant == tenant_id, Document.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def list_by_tenant(
    db: AsyncSession,
    tenant_id: UUID,
    page: int,
    page_size: int,
    search: str | None = None,
    status: str | None = None,
    project_id: UUID | None = None,
) -> tuple[list[Document], int]:
    base = select(Document).where(Document.id_tenant == tenant_id, Document.deleted_at.is_(None))

    if project_id:
        base = base.where(Document.id_project == project_id)
    if search:
        base = base.where(Document.name.ilike(f"%{search}%"))
    if status:
        base = base.where(Document.status == status)

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total = count_result.scalar_one()

    result = await db.execute(
        base.order_by(Document.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    return list(result.scalars().all()), total


async def create(
    db: AsyncSession,
    id_project: UUID,
    id_tenant: UUID,
    name: str,
    type: str,
    storage_path: str | None = None,
) -> Document:
    document = Document(
        id_project=id_project,
        id_tenant=id_tenant,
        name=name,
        type=type,
        storage_path=storage_path,
    )
    db.add(document)
    await db.flush()
    return document


async def update(db: AsyncSession, document: Document, **fields) -> Document:
    for key, value in fields.items():
        if hasattr(document, key) and key != "status":
            setattr(document, key, value)
    await db.flush()
    return document


async def update_status(
    db: AsyncSession, document: Document, status: str, error_msg: str | None = None
) -> Document:
    document.status = status
    document.error_msg = error_msg
    await db.flush()
    return document


async def soft_delete(db: AsyncSession, document: Document) -> None:
    document.deleted_at = func.now()
    await db.flush()
