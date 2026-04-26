from dataclasses import dataclass, field
from uuid import UUID

from fastapi import Query


@dataclass
class TenantContext:
    tenant_id: UUID
    api_key_id: UUID
    gemini_api_key: str | None = field(default=None)


@dataclass
class PaginationParams:
    page: int = Query(1, ge=1)
    page_size: int = Query(20, ge=1, le=100)
