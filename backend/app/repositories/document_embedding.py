from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_embedding import DocumentEmbedding


async def create_bulk(db: AsyncSession, embeddings: list[dict]) -> None:
    objects = [DocumentEmbedding(**data) for data in embeddings]
    db.add_all(objects)
    await db.flush()


async def delete_by_document(db: AsyncSession, document_id: UUID) -> None:
    await db.execute(
        delete(DocumentEmbedding).where(DocumentEmbedding.id_document == document_id)
    )
    await db.flush()


async def similarity_search(
    db: AsyncSession,
    embedding: list[float],
    project_id: UUID,
    tenant_id: UUID,
    limit: int = 10,
) -> list[tuple[DocumentEmbedding, float]]:
    distance = DocumentEmbedding.embedding.cosine_distance(embedding).label("distance")
    result = await db.execute(
        select(DocumentEmbedding, distance)
        .where(
            DocumentEmbedding.id_project == project_id,
            DocumentEmbedding.id_tenant == tenant_id,
        )
        .order_by(distance)
        .limit(limit)
    )
    return [(row[0], float(row[1])) for row in result.all()]
