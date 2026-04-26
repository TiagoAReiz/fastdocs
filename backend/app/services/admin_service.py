import hashlib
import secrets
from uuid import UUID

from fastapi import HTTPException, status
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.models.api_key import ApiKey
from app.models.tenant import Tenant
from app.repositories import api_key as api_key_repo
from app.repositories import tenant as tenant_repo
from app.schemas.admin import (
    ApiKeyCreateResponse,
    ApiKeyResponse,
    TenantCreate,
    TenantCreateResponse,
    TenantListResponse,
    TenantResponse,
    TenantUpdate,
)


def _tenant_response(tenant: Tenant) -> TenantResponse:
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        webhook_url=tenant.webhook_url,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


def _api_key_response(api_key: ApiKey) -> ApiKeyResponse:
    return ApiKeyResponse(
        id=api_key.id,
        label=api_key.label,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
    )


async def _validate_gemini_key(api_key: str) -> None:
    try:
        await GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=api_key,
            output_dimensionality=settings.EMBEDDING_DIM,
            task_type="RETRIEVAL_QUERY",
        ).aembed_query("ping")
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Gemini API key: {exc}",
        )


def _generate_api_key() -> tuple[str, str]:
    """Returns (plaintext, sha256_hash)."""
    plain = f"fdocs_{secrets.token_hex(32)}"
    hash_key = hashlib.sha256(plain.encode()).hexdigest()
    return plain, hash_key


async def create_tenant(db: AsyncSession, body: TenantCreate) -> TenantCreateResponse:
    plain_gemini = body.gemini_api_key.get_secret_value()
    await _validate_gemini_key(plain_gemini)

    existing = await tenant_repo.get_by_name(db, body.name)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant name already exists")

    tenant = await tenant_repo.create(
        db,
        name=body.name,
        gemini_api_key_encrypted=encrypt(plain_gemini),
    )
    if body.webhook_url:
        await tenant_repo.update(db, tenant, webhook_url=body.webhook_url)

    plain_key, hash_key = _generate_api_key()
    await api_key_repo.create(db, tenant.id, hash_key, label="default")
    await db.commit()
    await db.refresh(tenant)

    return TenantCreateResponse(
        id=tenant.id,
        name=tenant.name,
        webhook_url=tenant.webhook_url,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
        api_key=plain_key,
    )


async def list_tenants(db: AsyncSession, page: int, page_size: int) -> TenantListResponse:
    tenants, total = await tenant_repo.list_paginated(db, page, page_size)
    return TenantListResponse(
        tenants=[_tenant_response(t) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
    )


async def _get_or_404(db: AsyncSession, id: UUID) -> Tenant:
    tenant = await tenant_repo.get_by_id(db, id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return tenant


async def get_tenant(db: AsyncSession, id: UUID) -> TenantResponse:
    return _tenant_response(await _get_or_404(db, id))


async def update_tenant(db: AsyncSession, id: UUID, body: TenantUpdate) -> TenantResponse:
    tenant = await _get_or_404(db, id)
    fields: dict = {}

    if body.name is not None:
        existing = await tenant_repo.get_by_name(db, body.name)
        if existing and existing.id != id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant name already exists")
        fields["name"] = body.name

    if body.gemini_api_key is not None:
        plain_gemini = body.gemini_api_key.get_secret_value()
        await _validate_gemini_key(plain_gemini)
        fields["gemini_api_key_encrypted"] = encrypt(plain_gemini)

    if body.webhook_url is not None:
        fields["webhook_url"] = body.webhook_url

    if fields:
        await tenant_repo.update(db, tenant, **fields)

    await db.commit()
    await db.refresh(tenant)
    return _tenant_response(tenant)


async def delete_tenant(db: AsyncSession, id: UUID) -> None:
    tenant = await _get_or_404(db, id)
    await tenant_repo.soft_delete(db, tenant)
    await db.commit()


async def emit_api_key(db: AsyncSession, id_tenant: UUID, label: str | None) -> ApiKeyCreateResponse:
    await _get_or_404(db, id_tenant)
    plain_key, hash_key = _generate_api_key()
    api_key = await api_key_repo.create(db, id_tenant, hash_key, label=label)
    await db.commit()
    await db.refresh(api_key)
    return ApiKeyCreateResponse(
        id=api_key.id,
        label=api_key.label,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        api_key=plain_key,
    )


async def list_api_keys(db: AsyncSession, id_tenant: UUID) -> list[ApiKeyResponse]:
    await _get_or_404(db, id_tenant)
    keys = await api_key_repo.list_by_tenant(db, id_tenant)
    return [_api_key_response(k) for k in keys]


async def revoke_api_key(db: AsyncSession, id: UUID) -> None:
    api_key = await api_key_repo.get_by_id(db, id)
    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    await api_key_repo.revoke(db, api_key)
    await db.commit()
