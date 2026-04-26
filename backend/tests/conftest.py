import hashlib
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# Set admin/crypto env vars before app modules are first imported
os.environ.setdefault("ENCRYPTION_KEY", Fernet.generate_key().decode())
os.environ.setdefault("SERVICE_API_KEY", "test-service-key")
os.environ.setdefault("ADMIN_ALLOWED_IPS", '["127.0.0.1"]')

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.api_key import ApiKey
from app.models.chat_thread import ChatThread
from app.models.document import Document
from app.models.project import Project
from app.models.tenant import Tenant


def _make_test_db_url(url: str) -> str:
    base, _dbname = url.rsplit("/", 1)
    return f"{base}/fastdocs_test"


TEST_DB_URL_ASYNC = _make_test_db_url(settings.DATABASE_URL)
TEST_DB_URL_SYNC = TEST_DB_URL_ASYNC.replace("+asyncpg", "")

engine_test = create_async_engine(TEST_DB_URL_ASYNC, echo=False, poolclass=NullPool)
async_session_test = async_sessionmaker(
    engine_test, class_=AsyncSession, expire_on_commit=False
)


# Use a SYNC engine for table creation/drop to avoid event-loop scoping issues.
@pytest.fixture(scope="session", autouse=True)
def setup_db():
    sync_engine = create_engine(TEST_DB_URL_SYNC, echo=False)
    with sync_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.drop_all(bind=conn)
        Base.metadata.create_all(bind=conn)
    yield
    with sync_engine.begin() as conn:
        Base.metadata.drop_all(bind=conn)
    sync_engine.dispose()


@pytest_asyncio.fixture
async def db():
    """Standalone session for direct repo/service unit tests."""
    async with async_session_test() as session:
        yield session
        await session.rollback()


# ---- Entity fixtures ----
# Commit data so the client (which uses a separate session) can see it.


def _encrypted_dummy_key() -> str:
    from app.core.crypto import encrypt
    return encrypt("AIzaDummyKeyForTests")


@pytest_asyncio.fixture
async def tenant(db: AsyncSession):
    t = Tenant(name=f"test-tenant-{uuid.uuid4().hex[:8]}", gemini_api_key_encrypted=_encrypted_dummy_key())
    db.add(t)
    await db.commit()
    return t


@pytest_asyncio.fixture
async def second_tenant(db: AsyncSession):
    t = Tenant(name=f"test-tenant-b-{uuid.uuid4().hex[:8]}", gemini_api_key_encrypted=_encrypted_dummy_key())
    db.add(t)
    await db.commit()
    return t


@pytest_asyncio.fixture
async def api_key_plain(db: AsyncSession, tenant: Tenant):
    """Returns (plain_key, ApiKey model)."""
    plain = f"fdocs_{uuid.uuid4().hex}"
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    key = ApiKey(id_tenant=tenant.id, hash_key=hashed, label="test")
    db.add(key)
    await db.commit()
    return plain, key


@pytest_asyncio.fixture
async def second_api_key_plain(db: AsyncSession, second_tenant: Tenant):
    plain = f"fdocs_{uuid.uuid4().hex}"
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    key = ApiKey(id_tenant=second_tenant.id, hash_key=hashed, label="test-b")
    db.add(key)
    await db.commit()
    return plain, key


@pytest_asyncio.fixture
def auth_headers(api_key_plain) -> dict[str, str]:
    plain, _ = api_key_plain
    return {"X-API-Key": plain}


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {
        "X-Service-Key": settings.SERVICE_API_KEY,
        "X-Forwarded-For": "127.0.0.1",
    }


@pytest_asyncio.fixture
async def project(db: AsyncSession, tenant: Tenant) -> Project:
    p = Project(id_tenant=tenant.id, name="Test Project")
    db.add(p)
    await db.commit()
    return p


@pytest_asyncio.fixture
async def document(db: AsyncSession, tenant: Tenant, project: Project) -> Document:
    doc = Document(
        id_project=project.id,
        id_tenant=tenant.id,
        name="test.pdf",
        type="pdf",
        storage_path=f"{tenant.id}/{project.id}/test.pdf",
    )
    db.add(doc)
    await db.commit()
    return doc


@pytest_asyncio.fixture
async def chat_thread(db: AsyncSession, tenant: Tenant, project: Project) -> ChatThread:
    thread = ChatThread(id_tenant=tenant.id, id_project=project.id, name="Test thread")
    db.add(thread)
    await db.commit()
    return thread


# ---- Client fixture ----


async def _override_get_db():
    async with async_session_test() as session:
        yield session


@pytest_asyncio.fixture
async def client():
    app.dependency_overrides[get_db] = _override_get_db
    mock_checkpointer = MagicMock()
    mock_checkpointer.saver = MagicMock()
    app.state.checkpointer = mock_checkpointer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---- Mock fixtures ----


@pytest.fixture
def mock_blob_container():
    mock_container = MagicMock()
    mock_container.upload_blob = MagicMock()
    mock_container.download_blob.return_value.readall.return_value = b"file content"
    with patch(
        "app.services.document_service.get_container_client",
        return_value=mock_container,
    ):
        yield mock_container


@pytest.fixture
def mock_rate_limit():
    async def _always_allow(*args, **kwargs):
        return True, {
            "X-RateLimit-Limit": "999",
            "X-RateLimit-Remaining": "999",
            "X-RateLimit-Reset": "0",
        }

    with patch("app.routers.deps.rate_limit_check", side_effect=_always_allow):
        yield


@pytest.fixture
def mock_redis_cache():
    cache: dict[str, object] = {}

    async def _get(key):
        return cache.get(key)

    async def _set(key, value, ttl=None):
        cache[key] = value

    async def _delete(key):
        cache.pop(key, None)

    async def _invalidate(tenant_id):
        to_remove = [k for k in cache if str(tenant_id) in k]
        for k in to_remove:
            cache.pop(k, None)

    with (
        patch("app.clients.redis_client.cache_get", side_effect=_get),
        patch("app.clients.redis_client.cache_set", side_effect=_set),
        patch("app.clients.redis_client.cache_delete", side_effect=_delete),
        patch("app.clients.redis_client.cache_invalidate_tenant", side_effect=_invalidate),
        patch("app.services.chat_service.cache_get", side_effect=_get),
        patch("app.services.chat_service.cache_set", side_effect=_set),
    ):
        yield cache
