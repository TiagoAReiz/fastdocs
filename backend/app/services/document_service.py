from pathlib import PurePosixPath
from uuid import UUID

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import get_container_client
from app.models.document import Document
from app.repositories import document as document_repo
from app.repositories import outbox_event as outbox_repo
from app.repositories import project as project_repo
from app.schemas.deps import TenantContext
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentStatus,
    DocumentSummary,
    DocumentUpdateRequest,
    DocumentUploadResponse,
)


def _extract_type(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lstrip(".").lower()
    return suffix or "bin"


def _to_summary(doc: Document) -> DocumentSummary:
    return DocumentSummary(
        id=doc.id,
        name=doc.name,
        type=doc.type,
        status=DocumentStatus(doc.status),
    )


def _to_detail(doc: Document) -> DocumentDetailResponse:
    metadata = None
    if doc.metadata_rel is not None:
        metadata = getattr(doc.metadata_rel, "data", None) or {}
    return DocumentDetailResponse(
        id=doc.id,
        name=doc.name,
        type=doc.type,
        status=DocumentStatus(doc.status),
        metadata=metadata,
    )


async def _get_or_404(db: AsyncSession, tenant: TenantContext, id: UUID) -> Document:
    doc = await document_repo.get_by_id(db, id, tenant.tenant_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


async def upload(
    db: AsyncSession,
    tenant: TenantContext,
    id_project: UUID,
    file: UploadFile,
) -> DocumentUploadResponse:
    project = await project_repo.get_by_id(db, id_project, tenant.tenant_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    filename = file.filename or "upload.bin"
    doc = await document_repo.create(
        db,
        id_project=id_project,
        id_tenant=tenant.tenant_id,
        name=filename,
        type=_extract_type(filename),
        storage_path=None,
    )

    blob_key = f"{tenant.tenant_id}/{doc.id}/{filename}"
    content = await file.read()
    container = get_container_client()
    container.upload_blob(name=blob_key, data=content, overwrite=True)

    await document_repo.update(db, doc, storage_path=blob_key)
    await outbox_repo.create(
        db,
        aggregate_id=doc.id,
        event_type="document.uploaded",
        payload={
            "id_document": str(doc.id),
            "id_tenant": str(tenant.tenant_id),
            "id_project": str(id_project),
        },
    )
    await db.commit()

    return DocumentUploadResponse(id_document=doc.id, status=DocumentStatus(doc.status))


async def list_documents(
    db: AsyncSession,
    tenant: TenantContext,
    page: int,
    page_size: int,
    search: str | None = None,
    doc_status: str | None = None,
) -> DocumentListResponse:
    items, total = await document_repo.list_by_tenant(
        db, tenant.tenant_id, page, page_size, search=search, status=doc_status
    )
    return DocumentListResponse(
        documents=[_to_summary(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


async def get(db: AsyncSession, tenant: TenantContext, id: UUID) -> DocumentDetailResponse:
    doc = await _get_or_404(db, tenant, id)
    return _to_detail(doc)


async def update(
    db: AsyncSession,
    tenant: TenantContext,
    id: UUID,
    body: DocumentUpdateRequest,
) -> DocumentDetailResponse:
    doc = await _get_or_404(db, tenant, id)
    fields = body.model_dump(exclude_unset=True)
    fields.pop("status", None)
    await document_repo.update(db, doc, **fields)
    await db.commit()
    await db.refresh(doc)
    return _to_detail(doc)


async def delete(db: AsyncSession, tenant: TenantContext, id: UUID) -> None:
    doc = await _get_or_404(db, tenant, id)
    await document_repo.soft_delete(db, doc)
    await db.commit()


async def reprocess(
    db: AsyncSession, tenant: TenantContext, id: UUID
) -> DocumentUploadResponse:
    doc = await _get_or_404(db, tenant, id)
    await document_repo.update_status(db, doc, status="pending", error_msg=None)
    await outbox_repo.create(
        db,
        aggregate_id=doc.id,
        event_type="document.reprocess",
        payload={
            "id_document": str(doc.id),
            "id_tenant": str(tenant.tenant_id),
            "id_project": str(doc.id_project),
        },
    )
    await db.commit()
    return DocumentUploadResponse(id_document=doc.id, status=DocumentStatus(doc.status))
