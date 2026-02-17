import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    applications,
    auth,
    coach,
    companies,
    contacts,
    credits,
    dashboard,
    health,
    jobs,
    marketplace,
    matches,
    preferences,
    privacy,
    search,
    usage,
    webhooks,
)
from app.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.usage import UsageTrackingMiddleware
from app.utils.exceptions import AppError

logger = logging.getLogger(__name__)

app = FastAPI(title="WarmPath", version="0.1.0")

# ---------------------------------------------------------------------------
# Startup configuration validation
# ---------------------------------------------------------------------------
if settings.SECURE_HEADERS:
    if settings.SECRET_KEY == "change-me-to-a-random-secret":
        logger.critical(
            "SECURE_HEADERS is enabled but SECRET_KEY is the default value. "
            "Set a random SECRET_KEY before deploying to production."
        )
    if not settings.ENCRYPTION_KEY:
        logger.critical(
            "SECURE_HEADERS is enabled but ENCRYPTION_KEY is empty. "
            "PII will be stored as plaintext. Set ENCRYPTION_KEY for production."
        )

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in _cors_origins else _cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------
app.add_middleware(SecurityHeadersMiddleware)

# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------
app.add_middleware(UsageTrackingMiddleware)

# ---------------------------------------------------------------------------
# Global exception handlers
# ---------------------------------------------------------------------------


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
            }
        },
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(contacts.router, prefix="/api/v1/contacts", tags=["contacts"])
app.include_router(companies.router, prefix="/api/v1/companies", tags=["companies"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
app.include_router(matches.router, prefix="/api/v1/matches", tags=["matches"])
app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
app.include_router(
    applications.router, prefix="/api/v1/applications", tags=["applications"]
)
app.include_router(
    preferences.router, prefix="/api/v1/preferences", tags=["preferences"]
)
app.include_router(
    marketplace.router, prefix="/api/v1/marketplace", tags=["marketplace"]
)
app.include_router(credits.router, prefix="/api/v1/credits", tags=["credits"])
app.include_router(usage.router, prefix="/api/v1/usage", tags=["usage"])
app.include_router(
    dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"]
)
app.include_router(coach.router, prefix="/api/v1/coach", tags=["coach"])
app.include_router(privacy.router, prefix="/api/v1/privacy", tags=["privacy"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])

# ---------------------------------------------------------------------------
# Frontend static files (SPA)
# ---------------------------------------------------------------------------
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if _frontend_dist.is_dir():
    app.mount(
        "/assets", StaticFiles(directory=_frontend_dist / "assets"), name="assets"
    )

    _frontend_dist_resolved = _frontend_dist.resolve()

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str) -> FileResponse:
        """Serve index.html for all non-API routes (SPA catch-all)."""
        file_path = (_frontend_dist / full_path).resolve()
        # Path containment: block traversal outside frontend/dist
        if not file_path.is_relative_to(_frontend_dist_resolved):
            return FileResponse(_frontend_dist / "index.html")
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
