import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    applications,
    auth,
    companies,
    contacts,
    credits,
    health,
    jobs,
    marketplace,
    matches,
    preferences,
    search,
    usage,
)
from app.config import settings
from app.middleware.usage import UsageTrackingMiddleware
from app.utils.exceptions import AppError

logger = logging.getLogger(__name__)

app = FastAPI(title="WarmPath", version="0.1.0")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
