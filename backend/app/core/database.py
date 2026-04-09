from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


_OUTBOX_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION notify_outbox() RETURNS trigger AS $$
BEGIN
  PERFORM pg_notify('outbox_channel', '');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql
"""

_OUTBOX_TRIGGER_DROP = "DROP TRIGGER IF EXISTS outbox_notify ON outbox_events"
_OUTBOX_TRIGGER_CREATE = (
    "CREATE TRIGGER outbox_notify AFTER INSERT ON outbox_events "
    "FOR EACH ROW EXECUTE FUNCTION notify_outbox()"
)


async def init_db():
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(_OUTBOX_TRIGGER_FN))
        await conn.execute(text(_OUTBOX_TRIGGER_DROP))
        await conn.execute(text(_OUTBOX_TRIGGER_CREATE))


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session
