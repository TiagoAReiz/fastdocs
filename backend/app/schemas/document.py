from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel


class DocumentStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    done = "done"
    error = "error"


class DocumentUploadResponse(BaseModel):
    id_document: UUID
    status: DocumentStatus


class DocumentSummary(BaseModel):
    id: UUID
    name: str
    type: str
    status: DocumentStatus


class DocumentListResponse(BaseModel):
    documents: list[DocumentSummary]
    total: int
    page: int
    page_size: int


class DocumentDetailResponse(BaseModel):
    id: UUID
    name: str
    type: str
    status: DocumentStatus
    metadata: dict | None = None


class DocumentUpdateRequest(BaseModel):
    name: str | None = None
    metadata: dict | None = None
