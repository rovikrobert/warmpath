import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    """Application health check — verifies API + Celery connectivity."""
    celery_status = "unavailable"
    try:
        from app.celery_app import celery_app

        result = celery_app.control.ping(timeout=2.0)
        if result:
            celery_status = "connected"
    except Exception:
        logger.debug("Celery ping failed", exc_info=True)

    return {
        "data": {"status": "healthy", "celery": celery_status},
        "meta": {},
    }
