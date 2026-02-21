import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    agents,
    applications,
    auth,
    benchmarks,
    clerk_webhooks,
    coach,
    companies,
    competitors,
    contacts,
    credits,
    dashboard,
    experiments,
    feed,
    feedback,
    friends,
    health,
    jobs,
    marketplace,
    matches,
    partnerships,
    preferences,
    privacy,
    referrals,
    registry,
    search,
    telegram,
    usage,
    webhooks,
)
from app.config import settings
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.usage import UsageTrackingMiddleware
from app.utils.error_reporter import send_error_alert
from app.utils.exceptions import AppError

logger = logging.getLogger(__name__)

app = FastAPI(title="WarmPath", version="0.1.0")

# ---------------------------------------------------------------------------
# Startup configuration validation
# ---------------------------------------------------------------------------
if settings.SECURE_HEADERS:
    _boot_errors: list[str] = []
    if not settings.ENCRYPTION_KEY:
        _boot_errors.append(
            "ENCRYPTION_KEY is empty — PII will be stored as plaintext."
        )
    if not settings.CLERK_SECRET_KEY:
        _boot_errors.append("CLERK_SECRET_KEY is not set.")
    if not settings.CLERK_DOMAIN:
        _boot_errors.append("CLERK_DOMAIN is not set.")
    if _boot_errors:
        for _err in _boot_errors:
            logger.critical("BOOT BLOCKED: %s", _err)
        raise RuntimeError(
            "Production boot blocked — fix these config issues: "
            + "; ".join(_boot_errors)
        )

if not settings.AI_MOCK_MODE:
    if not settings.ANTHROPIC_API_KEY.strip():
        raise RuntimeError(
            "AI_MOCK_MODE is disabled but ANTHROPIC_API_KEY is not set. "
            "Either set AI_MOCK_MODE=true or provide a valid API key."
        )
    if settings.CLEANUP_PROVIDER == "gemini" and not settings.GOOGLE_API_KEY.strip():
        raise RuntimeError("CLEANUP_PROVIDER=gemini but GOOGLE_API_KEY is not set.")
    # V2 pipeline: warn if no cleaning providers are configured
    if settings.CSV_PIPELINE_V2:
        has_any_provider = any(
            [
                settings.GOOGLE_API_KEY.strip(),
                settings.OPENAI_API_KEY.strip(),
                settings.GROQ_API_KEY.strip(),
                settings.DEEPSEEK_API_KEY.strip(),
            ]
        )
        if not has_any_provider:
            logger.warning(
                "CSV_PIPELINE_V2 enabled but no cleaning provider API keys set. "
                "AI cleaning will fall back to mock for all batches."
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


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Strip Pydantic v2 'input' and 'ctx' from 422 errors to prevent data leakage."""
    errors = []
    for err in exc.errors():
        clean = {k: v for k, v in err.items() if k not in ("input", "ctx", "url")}
        errors.append(clean)
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    # Telegram alert for founder (rate-limited per endpoint)
    user_hint = None
    try:
        from app.utils.security import verify_clerk_token

        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            payload = verify_clerk_token(auth_header[7:])
            clerk_id = payload.get("sub")
            if clerk_id:
                user_hint = f"clerk:{clerk_id}"
    except Exception:
        pass
    send_error_alert(request.method, request.url.path, exc, user_hint)

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
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(feed.router, prefix="/api/v1/feed", tags=["feed"])
app.include_router(coach.router, prefix="/api/v1/coach", tags=["coach"])
app.include_router(privacy.router, prefix="/api/v1/privacy", tags=["privacy"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["feedback"])
app.include_router(referrals.router, prefix="/api/v1/referrals", tags=["referrals"])
app.include_router(friends.router, prefix="/api/v1/friends", tags=["friends"])
app.include_router(registry.router, prefix="/api/v1/registry", tags=["registry"])
app.include_router(webhooks.router, prefix="/api/v1", tags=["webhooks"])
app.include_router(clerk_webhooks.router, prefix="/api/v1", tags=["clerk-webhooks"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(
    competitors.router, prefix="/api/v1/competitors", tags=["competitors"]
)
app.include_router(
    partnerships.router, prefix="/api/v1/partnerships", tags=["partnerships"]
)
app.include_router(
    experiments.router, prefix="/api/v1/experiments", tags=["experiments"]
)
app.include_router(benchmarks.router, prefix="/api/v1/benchmarks", tags=["benchmarks"])
app.include_router(telegram.router, prefix="/api/v1/telegram", tags=["telegram"])

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
