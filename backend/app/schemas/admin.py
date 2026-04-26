import uuid
from datetime import datetime

from pydantic import BaseModel, SecretStr


class TenantCreate(BaseModel):
    name: str
    gemini_api_key: SecretStr
    webhook_url: str | None = None


class TenantUpdate(BaseModel):
    name: str | None = None
    gemini_api_key: SecretStr | None = None
    webhook_url: str | None = None


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    webhook_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TenantCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    webhook_url: str | None
    created_at: datetime
    updated_at: datetime
    api_key: str  # plaintext — shown once

    model_config = {"from_attributes": True}


class TenantListResponse(BaseModel):
    tenants: list[TenantResponse]
    total: int
    page: int
    page_size: int


class ApiKeyCreate(BaseModel):
    label: str | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    label: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreateResponse(BaseModel):
    id: uuid.UUID
    label: str | None
    is_active: bool
    created_at: datetime
    api_key: str  # plaintext — shown once

    model_config = {"from_attributes": True}
