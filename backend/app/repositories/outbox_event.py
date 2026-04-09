from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from app.models.outbox_event import OutboxEvent


async def create(
    db: AsyncSession, aggregate_id: UUID, event_type: str, payload: dict
) -> OutboxEvent:
    event = OutboxEvent(aggregate_id=aggregate_id, event_type=event_type, payload=payload)
    db.add(event)
    await db.flush()
    return event


async def get_unpublished(db: AsyncSession, limit: int = 50) -> list[OutboxEvent]:
    result = await db.execute(
        select(OutboxEvent)
        .where(OutboxEvent.published.is_(False))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_published(db: AsyncSession, event_id: UUID) -> None:
    result = await db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id))
    event = result.scalar_one()
    event.published = True
    event.published_at = func.now()
    await db.flush()
