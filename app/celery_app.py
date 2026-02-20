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
        # --- Feed generation (engagement engine) ---
        "feed-generate-morning": {
            "task": "app.tasks.feed_tasks.generate_feed_all_users",
            "schedule": crontab(hour=7, minute=0),  # 7 AM UTC — before work
        },
        "feed-generate-midday": {
            "task": "app.tasks.feed_tasks.generate_feed_all_users",
            "schedule": crontab(hour=13, minute=0),  # 1 PM UTC — lunch check
        },
        "feed-generate-evening": {
            "task": "app.tasks.feed_tasks.generate_feed_all_users",
            "schedule": crontab(hour=19, minute=0),  # 7 PM UTC — evening check
        },
        "feed-cleanup-weekly": {
            "task": "app.tasks.feed_tasks.cleanup_expired_feed_items",
            "schedule": crontab(day_of_week=0, hour=3, minute=0),  # Sunday 3 AM
        },
        "feed-smart-digest-mon": {
            "task": "app.tasks.feed_tasks.send_smart_digest",
            "schedule": crontab(day_of_week=1, hour=8, minute=30),  # Monday 8:30 AM
        },
        "feed-smart-digest-thu": {
            "task": "app.tasks.feed_tasks.send_smart_digest",
            "schedule": crontab(day_of_week=4, hour=8, minute=30),  # Thursday 8:30 AM
        },
    },
)
celery_app.autodiscover_tasks(["app.tasks"])
