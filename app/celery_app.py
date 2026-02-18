from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery("warmpath")
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    beat_schedule={
        "csv-reminder-d1": {
            "task": "app.tasks.email_tasks.send_csv_reminder_d1",
            "schedule": crontab(hour=9, minute=0),
        },
        "csv-reminder-d3": {
            "task": "app.tasks.email_tasks.send_csv_reminder_d3",
            "schedule": crontab(hour=9, minute=15),
        },
        "nh-sharing-d2": {
            "task": "app.tasks.email_tasks.send_nh_sharing_d2",
            "schedule": crontab(hour=10, minute=0),
        },
        "first-search-d2": {
            "task": "app.tasks.email_tasks.send_first_search_d2",
            "schedule": crontab(hour=10, minute=15),
        },
        "intro-pending-24h": {
            "task": "app.tasks.email_tasks.send_intro_pending_24h",
            "schedule": crontab(minute=0),  # every hour
        },
        "weekly-digest": {
            "task": "app.tasks.email_tasks.send_weekly_digest",
            "schedule": crontab(day_of_week=1, hour=8, minute=0),
        },
        "reengagement-d30": {
            "task": "app.tasks.email_tasks.send_reengagement_d30",
            "schedule": crontab(hour=9, minute=30),
        },
        "reengagement-d90": {
            "task": "app.tasks.email_tasks.send_reengagement_d90",
            "schedule": crontab(hour=9, minute=45),
        },
    },
)
celery_app.autodiscover_tasks(["app.tasks"])
