from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "fastdocs",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
)

celery_app.conf.beat_schedule = {
    "recover-stuck-docs": {
        "task": "app.services.beat_tasks.recover_stuck_documents",
        "schedule": 60.0,
    },
}

celery_app.autodiscover_tasks(["app.services"])

# Explicit imports — autodiscover only finds modules named `tasks.py`.
import app.services.beat_tasks  # noqa: E402,F401
import app.services.ingestion_tasks  # noqa: E402,F401
import app.services.webhook_tasks  # noqa: E402,F401
