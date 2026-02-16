"""Usage tracking middleware.

Logs every authenticated API request to the usage_logs table.
For specific actions (csv_upload, search_run, intro_draft), additional
metadata like processing time is captured.

Also handles **metering** for 7 high-value actions — writes a second
log entry with resource_type="metered" and adds tier-aware warning
headers (X-WarmPath-Usage-Warning). Both operations use the same DB
session to avoid BaseHTTPMiddleware stacking issues.
"""

import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.middleware.usage_logger import compute_metering_warning, match_metered_action
from app.models.enrichment import UsageLog
from app.utils.security import decode_access_token


# Map (method, path_prefix) to (action, resource_type)
_ACTION_MAP: list[tuple[str, str, str, str]] = [
    ("POST", "/api/v1/contacts/upload", "csv_upload", "contact"),
    ("POST", "/api/v1/contacts/compute-scores", "compute_scores", "contact"),
    ("POST", "/api/v1/search", "search_create", "search"),
    ("GET", "/api/v1/search", "search_list", "search"),
    ("POST", "/api/v1/matches/intros", "intro_draft", "intro"),
    ("GET", "/api/v1/matches/intros", "intro_view", "intro"),
    ("PATCH", "/api/v1/matches/intros", "intro_update", "intro"),
    ("GET", "/api/v1/contacts", "contacts_list", "contact"),
    ("DELETE", "/api/v1/contacts", "contact_delete", "contact"),
    ("GET", "/api/v1/companies", "companies_list", "company"),
]

# Actions that trigger /run on searches
_SEARCH_RUN_PREFIX = "/api/v1/search/"
_SEARCH_RUN_SUFFIX = "/run"


def _classify_request(method: str, path: str) -> tuple[str, str]:
    """Classify a request into (action, resource_type)."""
    # Special case: POST /search/{id}/run
    if (
        method == "POST"
        and path.startswith(_SEARCH_RUN_PREFIX)
        and path.endswith(_SEARCH_RUN_SUFFIX)
    ):
        return "search_run", "search"

    for map_method, prefix, action, resource_type in _ACTION_MAP:
        if method == map_method and path.startswith(prefix):
            return action, resource_type

    return "api_call", "unknown"


def _extract_user_id(request: Request) -> uuid.UUID | None:
    """Try to extract user_id from Bearer token without raising."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        return decode_access_token(auth[7:])
    except Exception:
        return None


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # Skip non-API paths and health checks
        path = request.url.path
        if not path.startswith("/api/") or path == "/health":
            return await call_next(request)

        start = time.monotonic()
        response = await call_next(request)
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)

        # Only log authenticated requests (successful ones)
        user_id = _extract_user_id(request)
        if user_id is None:
            return response

        action, resource_type = _classify_request(request.method, path)
        metered_action = match_metered_action(request.method, path)
        ip_address = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent", "")[:500]

        metadata = {
            "method": request.method,
            "path": path,
            "status_code": response.status_code,
            "processing_time_ms": elapsed_ms,
        }

        # Log in a separate session to avoid interfering with the request's
        # own transaction. Respects dependency overrides for testing.
        try:
            from app.database import get_db
            from app.main import app as _app

            db_dep = _app.dependency_overrides.get(get_db, get_db)
            async for db in db_dep():
                # ---- broad tracking log ----
                log = UsageLog(
                    user_id=user_id,
                    action=action,
                    resource_type=resource_type,
                    metadata_=metadata,
                    ip_address=str(ip_address) if ip_address else None,
                    user_agent=user_agent,
                )
                db.add(log)

                # ---- metering log + warning header ----
                if metered_action is not None:
                    metered_log = UsageLog(
                        user_id=user_id,
                        action=metered_action,
                        resource_type="metered",
                        metadata_=metadata,
                        ip_address=str(ip_address) if ip_address else None,
                        user_agent=user_agent,
                    )
                    db.add(metered_log)
                    await db.flush()

                    warning = await compute_metering_warning(
                        user_id, metered_action, db
                    )
                    if warning:
                        response.headers["X-WarmPath-Usage-Warning"] = warning

                await db.commit()
                break
        except Exception:
            # Never let usage logging break the actual request
            pass

        return response
