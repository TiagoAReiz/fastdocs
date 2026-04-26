import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.clients.llm_client import generate_embeddings_batched
from app.clients.redis_client import cache_invalidate_tenant
from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.storage import get_container_client
from app.repositories import (
    document as document_repo,
    document_embedding as embedding_repo,
    document_metadata as document_metadata_repo,
    tenant as tenant_repo,
)
from app.services.extraction import chunker, cleaner, registry
from app.services.extraction.base import Chunk

log = logging.getLogger(__name__)


def _new_session_factory() -> async_sessionmaker[AsyncSession]:
    """Build a fresh engine + sessionmaker bound to the current event loop.

    Celery is sync; each task wraps an `asyncio.run(...)` and gets its own loop.
    asyncpg connections are loop-bound, so we cannot reuse the module-level engine.
    """
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(
    name="app.services.ingestion_tasks.process_document",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def process_document(
    self,
    id_document: str,
    id_tenant: str,
    id_project: str,
    **_: object,
) -> dict:
    return asyncio.run(
        _process_document_async(UUID(id_document), UUID(id_tenant), UUID(id_project))
    )


async def _process_document_async(
    id_document: UUID, id_tenant: UUID, id_project: UUID
) -> dict:
    session_factory = _new_session_factory()

    async with session_factory() as db:
        tenant = await tenant_repo.get_by_id(db, id_tenant)
        if tenant is None or not tenant.gemini_api_key_encrypted:
            log.error("process_document: tenant %s has no Gemini API key configured", id_tenant)
            async with session_factory() as err_db:
                doc_err = await document_repo.get_by_id(err_db, id_document, id_tenant)
                if doc_err:
                    doc_err.status = "error"
                    doc_err.error_msg = "Tenant has no Gemini API key configured"
                    await err_db.commit()
            return {"status": "error", "reason": "no_gemini_key"}

        from app.core.crypto import decrypt
        gemini_api_key = decrypt(tenant.gemini_api_key_encrypted)

        doc = await document_repo.get_by_id(db, id_document, id_tenant)
        if doc is None:
            log.warning("process_document: document %s not found", id_document)
            return {"status": "missing"}

        if not doc.storage_path:
            await document_repo.update_status(db, doc, "error", error_msg="missing storage_path")
            await db.commit()
            return {"status": "error", "reason": "missing storage_path"}

        doc.status = "processing"
        doc.error_msg = None
        await db.flush()
        await db.commit()

        try:
            content = _download_blob(doc.storage_path)

            result = registry.extract(doc.type, content)
            cleaned_sections = cleaner.clean_sections(result.sections)
            chunks: list[Chunk] = chunker.chunk(cleaned_sections)

            if not chunks:
                doc.status = "error"
                doc.error_msg = "no extractable content"
                doc.extraction_method = result.extraction_method
                await db.flush()
                await db.commit()
                return {"status": "error", "reason": "empty"}

            texts = [c.text for c in chunks]
            vectors = await generate_embeddings_batched(texts, gemini_api_key)
            if len(vectors) != len(chunks):
                raise RuntimeError(
                    f"embedding count mismatch: {len(vectors)} vs {len(chunks)} chunks"
                )

            await embedding_repo.delete_by_document(db, doc.id)
            await embedding_repo.create_bulk(
                db,
                [
                    {
                        "id_document": doc.id,
                        "id_tenant": id_tenant,
                        "id_project": id_project,
                        "content": chunk.text,
                        "embedding": vector,
                        "chunk_index": chunk.chunk_index,
                        "meta": chunk.metadata,
                    }
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ],
            )

            await document_metadata_repo.upsert(
                db,
                doc.id,
                {
                    **result.document_metadata,
                    "chunk_count": len(chunks),
                    "file_size": len(content),
                    "extraction_method": result.extraction_method,
                },
            )

            doc.status = "done"
            doc.extraction_method = result.extraction_method
            doc.extraction_notes = result.extraction_notes or None
            doc.error_msg = None
            await db.flush()
            await db.commit()

            await cache_invalidate_tenant(id_tenant)
            await _dispatch_webhook(session_factory, id_tenant, id_document, "done")

            return {"status": "done", "chunks": len(chunks)}

        except Exception as exc:  # noqa: BLE001
            log.exception("process_document failed for %s", id_document)
            await db.rollback()
            async with session_factory() as recovery_db:
                doc2 = await document_repo.get_by_id(recovery_db, id_document, id_tenant)
                if doc2 is not None:
                    doc2.status = "error"
                    doc2.error_msg = str(exc)[:500]
                    doc2.retry_count = (doc2.retry_count or 0) + 1
                    await recovery_db.flush()
                    await recovery_db.commit()
            raise


async def _dispatch_webhook(
    session_factory: async_sessionmaker[AsyncSession],
    id_tenant: UUID,
    id_document: UUID,
    doc_status: str,
    error: str | None = None,
) -> None:
    from datetime import datetime, timezone

    async with session_factory() as db:
        tenant = await tenant_repo.get_by_id(db, id_tenant)
    if tenant is None or not tenant.webhook_url:
        return

    payload = {
        "event": "document.processed",
        "document_id": str(id_document),
        "status": doc_status,
        "error": error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    celery_app.send_task(
        "app.services.webhook_tasks.send_webhook",
        kwargs={
            "webhook_url": tenant.webhook_url,
            "webhook_secret": tenant.webhook_secret,
            "payload": payload,
        },
    )


def _download_blob(storage_path: str) -> bytes:
    container = get_container_client()
    return container.download_blob(storage_path).readall()
