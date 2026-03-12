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
    task_soft_time_limit=300,
    task_time_limit=360,
    worker_max_tasks_per_child=50,
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
        "credit-expiry-nudge-daily": {
            "task": "app.tasks.email_tasks.send_credit_expiry_nudge",
            "schedule": crontab(hour=9, minute=30),
        },
        # --- Cross-user freshness aggregation (before feed generation) ---
        "freshness-aggregation-daily": {
            "task": "app.tasks.feed_tasks.aggregate_freshness",
            "schedule": crontab(hour=5, minute=0),  # 5 AM UTC — before 7 AM feed gen
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
        # --- Feed ranking weight recomputation ---
        "feed-recompute-weights": {
            "task": "app.tasks.feed_tasks.recompute_feed_weights",
            "schedule": crontab(hour="0,6,12,18", minute=30),  # Every 6 hours
        },
        # --- Rate limiter token recovery ---
        "rate-limiter-watchdog": {
            "task": "app.tasks.infra_tasks.rate_limiter_watchdog",
            "schedule": crontab(minute="*/5"),  # Every 5 minutes
        },
        "redis-stream-janitor": {
            "task": "app.tasks.infra_tasks.redis_stream_janitor",
            "schedule": crontab(minute="*/30"),  # Every 30 minutes
        },
        "stuck-upload-watchdog": {
            "task": "app.tasks.infra_tasks.stuck_upload_watchdog",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        # --- Job cache warming (recommendations data) ---
        "job-cache-warm": {
            "task": "app.tasks.job_scan_tasks.warm_job_cache_global",
            "schedule": crontab(hour="1,5,9,13,17,21", minute=0),  # Every 4 hours
        },
        # --- Vector search reindex ---
        "vector-full-reindex": {
            "task": "app.tasks.vector_tasks.full_vector_reindex",
            "schedule": crontab(hour=3, minute=0),
        },
        # --- Agent runtime: Railway log polling ---
        "agent-runtime-railway-poll": {
            "task": "app.tasks.agent_runtime_tasks.poll_railway_logs",
            "schedule": crontab(minute="*/15"),  # Every 15 minutes
        },
        # --- Agent runtime: Scheduled scans ---
        "agent-runtime-daily-scan": {
            "task": "app.tasks.agent_runtime_tasks.dispatch_scheduled_scan",
            "schedule": crontab(hour=4, minute=0),  # 4 AM UTC daily
            "kwargs": {"cadence": "daily"},
        },
        "agent-runtime-weekly-scan": {
            "task": "app.tasks.agent_runtime_tasks.dispatch_scheduled_scan",
            "schedule": crontab(day_of_week=0, hour=2, minute=0),  # Sunday 2 AM
            "kwargs": {"cadence": "weekly"},
        },
        # --- Agent runtime: KPI anomaly detection ---
        "agent-runtime-kpi-check": {
            "task": "app.tasks.agent_runtime_tasks.dispatch_kpi_check",
            "schedule": crontab(hour=6, minute=0),  # 6 AM UTC daily
        },
        # --- Daily DB performance report ---
        "daily-perf-report": {
            "task": "app.tasks.perf_report_tasks.daily_perf_report",
            "schedule": crontab(
                hour=4, minute=30
            ),  # 4:30 AM UTC — before business hours
        },
        # --- Qdrant free-tier keep-alive (every 3 days) ---
        "qdrant-keep-alive": {
            "task": "app.tasks.infra_tasks.qdrant_keep_alive",
            "schedule": crontab(
                hour=4, minute=30, day_of_month="1,4,7,10,13,16,19,22,25,28"
            ),
        },
        # --- Production monitor health checks ---
        "monitor-health-check": {
            "task": "monitor.run_health_check",
            "schedule": 300.0,  # Every 5 minutes
        },
        # --- Celery backlog monitoring ---
        "celery-backlog-check": {
            "task": "monitor.celery_backlog_check",
            "schedule": 300.0,  # Every 5 minutes
        },
    },
)
celery_app.conf.include = [
    "app.tasks.csv_processing",
    "app.tasks.csv_pipeline",
    "app.tasks.email_tasks",
    "app.tasks.feed_tasks",
    "app.tasks.infra_tasks",
    "app.tasks.job_scan_tasks",
    "app.tasks.vector_tasks",
    "app.tasks.agent_runtime_tasks",
    "app.tasks.monitor_tasks",
    "app.tasks.perf_report_tasks",
]
