import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.document import Document
from app.repositories import outbox_event as outbox_repo

log = logging.getLogger(__name__)

STUCK_THRESHOLD_MINUTES = 10
MAX_RETRY_COUNT = 3


def _new_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.services.beat_tasks.recover_stuck_documents")
def recover_stuck_documents() -> dict:
    return asyncio.run(_recover_stuck_documents_async())


async def _recover_stuck_documents_async() -> dict:
    session_factory = _new_session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    recovered = 0
    failed = 0

    async with session_factory() as db:
        result = await db.execute(
            select(Document).where(
                Document.status == "processing",
                Document.updated_at < cutoff,
                Document.deleted_at.is_(None),
            )
        )
        stuck_docs = list(result.scalars().all())

        for doc in stuck_docs:
            if (doc.retry_count or 0) >= MAX_RETRY_COUNT:
                doc.status = "error"
                doc.error_msg = "max retries exceeded (stuck in processing)"
                failed += 1
                log.warning("document %s marked as error after %d retries", doc.id, doc.retry_count)
            else:
                doc.status = "pending"
                doc.retry_count = (doc.retry_count or 0) + 1
                await outbox_repo.create(
                    db,
                    aggregate_id=doc.id,
                    event_type="document.reprocess",
                    payload={
                        "id_document": str(doc.id),
                        "id_tenant": str(doc.id_tenant),
                        "id_project": str(doc.id_project),
                    },
                )
                recovered += 1
                log.info("document %s reset to pending (retry %d)", doc.id, doc.retry_count)

        if stuck_docs:
            await db.commit()

    return {"recovered": recovered, "failed": failed}
