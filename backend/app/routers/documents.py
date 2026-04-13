from uuid import UUID

from fastapi import APIRouter, Depends, Form, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.routers.deps import get_current_tenant, rate_limit_ingest
from app.schemas.deps import PaginationParams, TenantContext
from app.schemas.document import (
    DocumentDetailResponse,
    DocumentListResponse,
    DocumentUpdateRequest,
    DocumentUploadResponse,
)
from app.services import document_service

router = APIRouter(prefix="/api/documents", tags=["Documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit_ingest)],
)
async def upload_document(
    file: UploadFile,
    id_project: UUID = Form(...),
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.upload(db, tenant, id_project, file)


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    pagination: PaginationParams = Depends(),
    search: str | None = None,
    doc_status: str | None = None,
    id_project: UUID | None = None,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.list_documents(
        db,
        tenant,
        pagination.page,
        pagination.page_size,
        search=search,
        doc_status=doc_status,
        id_project=id_project,
    )


@router.get("/{id}", response_model=DocumentDetailResponse)
async def get_document(
    id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.get(db, tenant, id)


@router.put("/{id}", response_model=DocumentDetailResponse)
async def update_document(
    id: UUID,
    body: DocumentUpdateRequest,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.update(db, tenant, id, body)


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    await document_service.delete(db, tenant, id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id}/reprocess",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_document(
    id: UUID,
    tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    return await document_service.reprocess(db, tenant, id)
