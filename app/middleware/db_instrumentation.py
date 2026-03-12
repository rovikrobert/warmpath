"""DB instrumentation middleware — tracks per-request query count and total DB time.

Uses raw ASGI implementation (not BaseHTTPMiddleware) to avoid stacking
issues with other BaseHTTPMiddleware subclasses.

SQLAlchemy events fire on the underlying sync engine (even for async engines).
Use ``install_db_instrumentation(engine.sync_engine)`` to attach listeners.
"""

import contextvars
import logging
import time
from typing import Any

from sqlalchemy import event
from starlette.types import ASGIApp, Receive, Scope, Send

from app.utils.query_budgets import get_budget

logger = logging.getLogger("perf.db")

_request_db_stats: contextvars.ContextVar[dict[str, Any] | None] = (
    contextvars.ContextVar("request_db_stats", default=None)
)


def get_db_stats() -> dict[str, Any] | None:
    """Return the current request's DB stats, or None if not in a request context."""
    return _request_db_stats.get()


# ---------------------------------------------------------------------------
# SQLAlchemy event listeners
# ---------------------------------------------------------------------------


def _before_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
    stats = _request_db_stats.get()
    if stats is not None:
        stats["_current_start"] = time.monotonic()


def _after_execute(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
    stats = _request_db_stats.get()
    if stats is not None:
        start = stats.pop("_current_start", None)
        if start is not None:
            stats["total_db_time_ms"] += (time.monotonic() - start) * 1000
            stats["query_count"] += 1


def install_db_instrumentation(sync_engine) -> None:  # noqa: ANN001
    """Attach before/after cursor-execute listeners to a *sync* engine."""
    event.listen(sync_engine, "before_cursor_execute", _before_execute)
    event.listen(sync_engine, "after_cursor_execute", _after_execute)


# ---------------------------------------------------------------------------
# ASGI middleware
# ---------------------------------------------------------------------------


class DBInstrumentationMiddleware:
    """Injects ``X-DB-Query-Count`` and ``X-DB-Time-Ms`` response headers for /api/ paths."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        token = _request_db_stats.set({"query_count": 0, "total_db_time_ms": 0.0})

        async def send_with_headers(message: dict) -> None:
            if message["type"] == "http.response.start":
                stats = _request_db_stats.get()
                if stats:
                    headers = list(message.get("headers", []))
                    headers.append(
                        (b"x-db-query-count", str(stats["query_count"]).encode())
                    )
                    headers.append(
                        (b"x-db-time-ms", f"{stats['total_db_time_ms']:.1f}".encode())
                    )
                    message = {**message, "headers": headers}

                    # Check query budget and log warning if exceeded
                    budget = get_budget(scope.get("method", ""), scope.get("path", ""))
                    if budget and stats["query_count"] > budget["max_queries"]:
                        logger.warning(
                            "QUERY_BUDGET_EXCEEDED: %s %s — %d queries (budget: %d)",
                            scope.get("method"),
                            scope.get("path"),
                            stats["query_count"],
                            budget["max_queries"],
                        )
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            _request_db_stats.reset(token)
