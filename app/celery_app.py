from celery import Celery

from app.config import settings

celery_app = Celery("warmpath")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)
celery_app.autodiscover_tasks(["app.tasks"])
