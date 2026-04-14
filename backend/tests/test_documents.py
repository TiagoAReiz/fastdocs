import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outbox_event import OutboxEvent
from app.models.project import Project


@pytest.mark.asyncio
async def test_upload_document(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    mock_blob_container,
    mock_rate_limit,
):
    file = io.BytesIO(b"fake pdf content")
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": str(project.id)},
        files={"file": ("report.pdf", file, "application/pdf")},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "id_document" in data
    assert data["status"] == "pending"
    mock_blob_container.upload_blob.assert_called_once()


@pytest.mark.asyncio
async def test_upload_creates_outbox_event(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    db: AsyncSession,
    mock_blob_container,
    mock_rate_limit,
):
    file = io.BytesIO(b"content")
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": str(project.id)},
        files={"file": ("doc.txt", file, "text/plain")},
    )
    assert resp.status_code == 202
    doc_id = resp.json()["id_document"]

    result = await db.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == doc_id,
            OutboxEvent.event_type == "document.uploaded",
        )
    )
    event = result.scalar_one_or_none()
    assert event is not None


@pytest.mark.asyncio
async def test_upload_invalid_project_404(
    client: AsyncClient,
    auth_headers: dict,
    mock_blob_container,
    mock_rate_limit,
):
    fake_project = str(uuid.uuid4())
    file = io.BytesIO(b"content")
    resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": fake_project},
        files={"file": ("doc.txt", file, "text/plain")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_documents_empty(
    client: AsyncClient,
    auth_headers: dict,
):
    resp = await client.get("/api/documents/", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_documents_filter_by_status(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    mock_blob_container,
    mock_rate_limit,
):
    file = io.BytesIO(b"content")
    await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": str(project.id)},
        files={"file": ("doc.txt", file, "text/plain")},
    )

    resp = await client.get(
        "/api/documents/",
        headers=auth_headers,
        params={"doc_status": "pending"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert all(d["status"] == "pending" for d in data["documents"])


@pytest.mark.asyncio
async def test_get_document(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    db: AsyncSession,
    tenant,
    mock_blob_container,
    mock_rate_limit,
):
    # Create document with metadata_rel pre-set to avoid lazy load issue
    from app.models.document import Document
    from app.models.document_metadata import DocumentMetadata

    doc = Document(
        id_project=project.id,
        id_tenant=tenant.id,
        name="doc.txt",
        type="txt",
        storage_path="some/path",
    )
    db.add(doc)
    await db.flush()
    meta = DocumentMetadata(id_document=doc.id, data={"test": True})
    db.add(meta)
    await db.commit()

    resp = await client.get(f"/api/documents/{doc.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "doc.txt"
    assert resp.json()["type"] == "txt"


@pytest.mark.asyncio
async def test_update_document_name(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    db: AsyncSession,
    tenant,
    mock_blob_container,
    mock_rate_limit,
):
    from app.models.document import Document
    from app.models.document_metadata import DocumentMetadata

    doc = Document(
        id_project=project.id,
        id_tenant=tenant.id,
        name="old_name.txt",
        type="txt",
        storage_path="some/path",
    )
    db.add(doc)
    await db.flush()
    meta = DocumentMetadata(id_document=doc.id, data={})
    db.add(meta)
    await db.commit()

    resp = await client.put(
        f"/api/documents/{doc.id}",
        headers=auth_headers,
        json={"name": "new_name.txt"},
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new_name.txt"


@pytest.mark.asyncio
async def test_delete_document(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    mock_blob_container,
    mock_rate_limit,
):
    file = io.BytesIO(b"content")
    upload_resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": str(project.id)},
        files={"file": ("del.txt", file, "text/plain")},
    )
    doc_id = upload_resp.json()["id_document"]

    resp = await client.delete(f"/api/documents/{doc_id}", headers=auth_headers)
    assert resp.status_code == 204

    get_resp = await client.get(f"/api/documents/{doc_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_reprocess_document(
    client: AsyncClient,
    auth_headers: dict,
    project: Project,
    db: AsyncSession,
    mock_blob_container,
    mock_rate_limit,
):
    file = io.BytesIO(b"content")
    upload_resp = await client.post(
        "/api/documents/upload",
        headers=auth_headers,
        data={"id_project": str(project.id)},
        files={"file": ("reprocess.txt", file, "text/plain")},
    )
    doc_id = upload_resp.json()["id_document"]

    resp = await client.post(f"/api/documents/{doc_id}/reprocess", headers=auth_headers)
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"

    result = await db.execute(
        select(OutboxEvent).where(
            OutboxEvent.aggregate_id == doc_id,
            OutboxEvent.event_type == "document.reprocess",
        )
    )
    assert result.scalar_one_or_none() is not None
