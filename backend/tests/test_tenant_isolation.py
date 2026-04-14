import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.project import Project
from app.models.tenant import Tenant
from app.repositories import document as document_repo
from app.repositories import project as project_repo


@pytest.mark.asyncio
async def test_project_isolation(
    db: AsyncSession, tenant: Tenant, second_tenant: Tenant
):
    # Create project under tenant A
    proj = await project_repo.create(db, tenant.id, "Tenant A Project")

    # Tenant A can see it
    found = await project_repo.get_by_id(db, proj.id, tenant.id)
    assert found is not None
    assert found.name == "Tenant A Project"

    # Tenant B cannot see it
    not_found = await project_repo.get_by_id(db, proj.id, second_tenant.id)
    assert not_found is None


@pytest.mark.asyncio
async def test_document_isolation(
    db: AsyncSession, tenant: Tenant, second_tenant: Tenant
):
    proj = await project_repo.create(db, tenant.id, "Doc Isolation Project")
    doc = await document_repo.create(
        db,
        id_project=proj.id,
        id_tenant=tenant.id,
        name="secret.pdf",
        type="pdf",
    )

    # Tenant A can see the document
    found = await document_repo.get_by_id(db, doc.id, tenant.id)
    assert found is not None

    # Tenant B cannot see the document
    not_found = await document_repo.get_by_id(db, doc.id, second_tenant.id)
    assert not_found is None


@pytest.mark.asyncio
async def test_list_isolation(
    db: AsyncSession, tenant: Tenant, second_tenant: Tenant
):
    # Create projects for tenant A
    for i in range(3):
        await project_repo.create(db, tenant.id, f"A-Project-{i}")

    # Tenant B should see none of tenant A's projects
    items, total = await project_repo.list_by_tenant(db, second_tenant.id, page=1, page_size=50)
    assert total == 0
    assert items == []

    # Tenant A should see all their own
    items_a, total_a = await project_repo.list_by_tenant(db, tenant.id, page=1, page_size=50)
    assert total_a >= 3
