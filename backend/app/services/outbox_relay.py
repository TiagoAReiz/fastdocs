"""Outbox relay process.

Listens on Postgres NOTIFY channel `outbox_channel` and falls back to a
periodic timeout. Each wake-up flushes any unpublished outbox events by
dispatching them to Celery and marking them as published.

Run with: ``python -m app.services.outbox_relay``
"""

import asyncio
import logging

import asyncpg

from app.core.celery_app import celery_app
from app.core.config import settings
from app.core.database import async_session
from app.repositories import outbox_event as outbox_repo

log = logging.getLogger("outbox_relay")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

CHANNEL = "outbox_channel"

_EVENT_TO_TASK = {
    "document.uploaded": "app.services.ingestion_tasks.process_document",
    "document.reprocess": "app.services.ingestion_tasks.process_document",
}


async def flush_unpublished() -> int:
    dispatched = 0
    async with async_session() as db:
        events = await outbox_repo.get_unpublished(
            db, limit=settings.OUTBOX_RELAY_BATCH_SIZE
        )
        for ev in events:
            task_name = _EVENT_TO_TASK.get(ev.event_type)
            if task_name is not None:
                payload = ev.payload or {}
                celery_app.send_task(task_name, kwargs=payload)
                dispatched += 1
            else:
                log.warning("no task mapping for event_type=%s", ev.event_type)
            await outbox_repo.mark_published(db, ev.id)
        await db.commit()
    if dispatched:
        log.info("flushed %d events", dispatched)
    return dispatched


async def main() -> None:
    log.info("connecting to %s", settings.DATABASE_URL_RAW)
    conn = await asyncpg.connect(settings.DATABASE_URL_RAW)

    wake = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _on_notify(*_args) -> None:
        loop.call_soon_threadsafe(wake.set)

    await conn.add_listener(CHANNEL, _on_notify)
    log.info("LISTEN %s — fallback poll every %ss", CHANNEL, settings.OUTBOX_RELAY_POLL_TIMEOUT)

    # Drain anything that arrived before we started.
    try:
        await flush_unpublished()
    except Exception:  # noqa: BLE001
        log.exception("initial flush failed")

    while True:
        try:
            await asyncio.wait_for(wake.wait(), timeout=settings.OUTBOX_RELAY_POLL_TIMEOUT)
        except asyncio.TimeoutError:
            pass
        wake.clear()
        try:
            await flush_unpublished()
        except Exception:  # noqa: BLE001
            log.exception("flush failed; will retry on next wake")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
