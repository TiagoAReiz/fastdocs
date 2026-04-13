import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.api_key import ApiKey
from app.models.tenant import Tenant

TEST_DB_URL = settings.DATABASE_URL.replace("/fastdocs", "/fastdocs_test")

engine_test = create_async_engine(TEST_DB_URL, echo=False)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine_test.dispose()


@pytest_asyncio.fixture
async def db():
    async with async_session_test() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def tenant(db: AsyncSession):
    t = Tenant(name=f"test-tenant-{uuid.uuid4().hex[:8]}")
    db.add(t)
    await db.flush()
    return t


@pytest_asyncio.fixture
async def api_key_plain(db: AsyncSession, tenant: Tenant):
    """Returns (plain_key, ApiKey model)."""
    plain = f"fdocs_{uuid.uuid4().hex}"
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    key = ApiKey(id_tenant=tenant.id, hash_key=hashed, label="test")
    db.add(key)
    await db.flush()
    return plain, key


async def _override_get_db():
    async with async_session_test() as session:
        yield session


@pytest_asyncio.fixture
async def client(db: AsyncSession):
    app.dependency_overrides[get_db] = _override_get_db
    # Mock the checkpointer to avoid needing Redis
    mock_checkpointer = MagicMock()
    mock_checkpointer.saver = MagicMock()
    app.state.checkpointer = mock_checkpointer
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
