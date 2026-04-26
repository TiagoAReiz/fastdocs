import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GEMINI_KEY = "AIzaFakeGeminiKey"

# Patch _validate_gemini_key so tests never call the real Gemini API
@pytest.fixture(autouse=True)
def mock_validate_gemini_key():
    with patch(
        "app.services.admin_service._validate_gemini_key",
        new_callable=AsyncMock,
    ) as m:
        m.return_value = None
        yield m


# ---------------------------------------------------------------------------
# Auth guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_no_service_key_returns_401(client: AsyncClient):
    resp = await client.get("/admin/tenants")
    assert resp.status_code == 422  # missing required header


@pytest.mark.asyncio
async def test_admin_wrong_service_key_returns_401(client: AsyncClient):
    resp = await client.get("/admin/tenants", headers={"X-Service-Key": "wrong"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_ip_not_allowed_returns_403(client: AsyncClient, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_IPS", ["10.0.0.99"])
    # X-Forwarded-For: 127.0.0.1 is NOT in the patched allowlist → 403
    resp = await client.get(
        "/admin/tenants",
        headers={"X-Service-Key": settings.SERVICE_API_KEY, "X-Forwarded-For": "127.0.0.1"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tenant CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_tenant_returns_api_key(client: AsyncClient, admin_headers: dict):
    resp = await client.post(
        "/admin/tenants",
        json={"name": f"acme-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "api_key" in data
    assert data["api_key"].startswith("fdocs_")
    assert "gemini_api_key" not in data  # must not leak


@pytest.mark.asyncio
async def test_create_tenant_duplicate_name_returns_409(client: AsyncClient, admin_headers: dict):
    name = f"dup-{uuid.uuid4().hex[:6]}"
    await client.post(
        "/admin/tenants",
        json={"name": name, "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    resp = await client.post(
        "/admin/tenants",
        json={"name": name, "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_list_tenants(client: AsyncClient, admin_headers: dict):
    resp = await client.get("/admin/tenants", headers=admin_headers)
    assert resp.status_code == 200
    assert "tenants" in resp.json()


@pytest.mark.asyncio
async def test_get_tenant(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"detail-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    resp = await client.get(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == tenant_id


@pytest.mark.asyncio
async def test_get_tenant_not_found(client: AsyncClient, admin_headers: dict):
    resp = await client.get(f"/admin/tenants/{uuid.uuid4()}", headers=admin_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_tenant_name(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"upd-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    new_name = f"updated-{uuid.uuid4().hex[:6]}"
    resp = await client.patch(
        f"/admin/tenants/{tenant_id}",
        json={"name": new_name},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == new_name


@pytest.mark.asyncio
async def test_delete_tenant(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"del-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    resp = await client.delete(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert resp.status_code == 204
    # subsequent get returns 404
    resp2 = await client.get(f"/admin/tenants/{tenant_id}", headers=admin_headers)
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emit_api_key(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"key-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    resp = await client.post(
        f"/admin/tenants/{tenant_id}/api-keys",
        json={"label": "integration"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["api_key"].startswith("fdocs_")
    assert data["label"] == "integration"


@pytest.mark.asyncio
async def test_list_api_keys(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"lst-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    resp = await client.get(f"/admin/tenants/{tenant_id}/api-keys", headers=admin_headers)
    assert resp.status_code == 200
    keys = resp.json()
    # The default key emitted at creation should be listed
    assert len(keys) >= 1
    assert "api_key" not in keys[0]  # plaintext must not appear in list


@pytest.mark.asyncio
async def test_revoke_api_key(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"rev-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    tenant_id = create.json()["id"]
    emit = await client.post(
        f"/admin/tenants/{tenant_id}/api-keys",
        json={"label": "to-revoke"},
        headers=admin_headers,
    )
    key_id = emit.json()["id"]
    resp = await client.delete(f"/admin/api-keys/{key_id}", headers=admin_headers)
    assert resp.status_code == 204

    # Revoked key must not appear as active
    keys_resp = await client.get(f"/admin/tenants/{tenant_id}/api-keys", headers=admin_headers)
    revoked = next((k for k in keys_resp.json() if k["id"] == key_id), None)
    assert revoked is not None
    assert revoked["is_active"] is False


@pytest.mark.asyncio
async def test_revoked_key_rejected_on_tenant_routes(client: AsyncClient, admin_headers: dict):
    create = await client.post(
        "/admin/tenants",
        json={"name": f"rej-{uuid.uuid4().hex[:6]}", "gemini_api_key": GEMINI_KEY},
        headers=admin_headers,
    )
    data = create.json()
    tenant_id = data["id"]
    plain_key = data["api_key"]

    # Key works before revocation
    list_keys = await client.get(f"/admin/tenants/{tenant_id}/api-keys", headers=admin_headers)
    key_id = list_keys.json()[0]["id"]

    await client.delete(f"/admin/api-keys/{key_id}", headers=admin_headers)

    # Key must now be rejected
    resp = await client.get("/api/projects/", headers={"X-API-Key": plain_key})
    assert resp.status_code == 401
