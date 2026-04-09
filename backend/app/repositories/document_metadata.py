from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_metadata import DocumentMetadata


async def get_by_document(db: AsyncSession, document_id: UUID) -> DocumentMetadata | None:
    result = await db.execute(
        select(DocumentMetadata).where(DocumentMetadata.id_document == document_id)
    )
    return result.scalar_one_or_none()


async def upsert(db: AsyncSession, document_id: UUID, metadata: dict) -> DocumentMetadata:
    existing = await get_by_document(db, document_id)
    if existing:
        existing.data = metadata
        await db.flush()
        return existing

    doc_metadata = DocumentMetadata(id_document=document_id, data=metadata)
    db.add(doc_metadata)
    await db.flush()
    return doc_metadata
