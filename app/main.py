import html as html_mod
import logging
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from app.api import (
    agent_webhooks,
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
    intro_review,
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
from app.middleware.db_instrumentation import (
    DBInstrumentationMiddleware,
    install_db_instrumentation,
)
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.usage import UsageTrackingMiddleware
from app.utils.error_reporter import send_error_alert
from app.utils.exceptions import AppError
from app.utils.weave_init import init_weave

logger = logging.getLogger(__name__)

app = FastAPI(title="WarmPath", version="0.1.0")

# ---------------------------------------------------------------------------
# Sentry error tracking (optional — gated on SENTRY_DSN)
# ---------------------------------------------------------------------------
if settings.SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        environment="production" if settings.is_production else "development",
    )

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
    _has_gemini = (
        settings.GOOGLE_API_KEY.strip() or settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip()
    )
    if settings.CLEANUP_PROVIDER == "gemini" and not _has_gemini:
        raise RuntimeError(
            "CLEANUP_PROVIDER=gemini but neither GOOGLE_API_KEY nor "
            "GOOGLE_SERVICE_ACCOUNT_JSON is set."
        )
    # V2 pipeline: warn if no cleaning providers are configured
    if settings.CSV_PIPELINE_V2:
        has_any_provider = any(
            [
                settings.GOOGLE_API_KEY.strip()
                or settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip(),
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
# W&B Weave AI observability (conditional)
# ---------------------------------------------------------------------------
init_weave()

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
# DB instrumentation (query count + timing per request)
# ---------------------------------------------------------------------------
app.add_middleware(DBInstrumentationMiddleware)

# ---------------------------------------------------------------------------
# Usage tracking
# ---------------------------------------------------------------------------
app.add_middleware(UsageTrackingMiddleware)

# ---------------------------------------------------------------------------
# Install DB event listeners for query instrumentation
# ---------------------------------------------------------------------------
try:
    from app.database import _get_engine

    install_db_instrumentation(_get_engine().sync_engine)
except Exception:
    logger.warning(
        "DB instrumentation listeners failed to install — per-request query "
        "count and timing will be unavailable. Health endpoint will report this "
        "as a degraded check.",
        exc_info=True,
    )

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
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        from fastapi import HTTPException as _HTTPException

        from app.utils.security import verify_clerk_token

        try:
            payload = verify_clerk_token(auth_header[7:])
            clerk_id = payload.get("sub")
            if clerk_id:
                user_hint = f"clerk:{clerk_id}"
        except _HTTPException:
            # Invalid/expired token — proceed with no user hint
            pass
        except Exception:
            logger.warning("Failed to extract user hint for error alert", exc_info=True)
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
app.include_router(intro_review.router, prefix="/api/v1", tags=["intro-review"])
app.include_router(
    agent_webhooks.router,
    prefix="/api/v1/agent-webhooks",
    tags=["agent-webhooks"],
)

# ---------------------------------------------------------------------------
# Social bot OG tag middleware (used by SPA catch-all)
# ---------------------------------------------------------------------------
_SOCIAL_BOT_FRAGMENTS = (
    "facebookexternalhit",
    "twitterbot",
    "linkedinbot",
    "slackbot",
    "discordbot",
    "whatsapp",
)


def _is_social_bot(request: Request) -> bool:
    """Return True if the request User-Agent belongs to a social link previewer."""
    ua = (request.headers.get("user-agent") or "").lower()
    return any(fragment in ua for fragment in _SOCIAL_BOT_FRAGMENTS)


def _get_og_config(path: str, params: dict[str, str]) -> dict[str, str] | None:
    """Return OG title/desc for a path, or None if path has no OG config."""
    if path == "join":
        if params.get("intent") == "seeker":
            return {
                "title": "Stop Applying Cold. Get Referred. \u2014 WarmPath",
                "description": (
                    "Employee referrals convert at 10-40% vs 1-3%. "
                    "Search anonymized networks at your target companies "
                    "and get warm introductions."
                ),
            }
        return {
            "title": "Share Your Network \u2014 WarmPath",
            "description": (
                "Help people get referred to jobs through your connections. "
                "Earn your employer\u2019s referral bonus ($2-10K per hire). "
                "Free, privacy-first, you stay in control."
            ),
        }
    if path.startswith("intro"):
        return {
            "title": "Introduction via WarmPath",
            "description": (
                "Someone in your network wants to connect you "
                "with a qualified professional."
            ),
        }
    return None


def _serve_og_html(path: str, params: dict[str, str]) -> HTMLResponse:
    """Return minimal HTML with OG meta tags for social bot crawlers."""
    config = _get_og_config(path, params)
    # Caller must verify config is not None before calling
    title = html_mod.escape(config["title"])  # type: ignore[index]
    description = html_mod.escape(config["description"])  # type: ignore[index]
    image_url = html_mod.escape(f"{settings.FRONTEND_URL}/og-image.png")
    page_url = f"{settings.FRONTEND_URL}/{path}"
    if params:
        qs = urlencode(params)
        page_url = f"{page_url}?{qs}"
    page_url = html_mod.escape(page_url)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{title}</title>
<meta property="og:type" content="website" />
<meta property="og:title" content="{title}" />
<meta property="og:description" content="{description}" />
<meta property="og:image" content="{image_url}" />
<meta property="og:url" content="{page_url}" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{title}" />
<meta name="twitter:description" content="{description}" />
<meta name="twitter:image" content="{image_url}" />
<meta http-equiv="refresh" content="0;url={page_url}" />
</head>
<body></body>
</html>"""
    return HTMLResponse(content=html)


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
    async def serve_spa(request: Request, full_path: str) -> Response:
        """Serve index.html for all non-API routes (SPA catch-all).

        Social bot crawlers receive minimal HTML with OG meta tags so that
        link previews on Facebook, Twitter, LinkedIn, Slack, Discord, and
        WhatsApp display the correct title, description, and image.
        """
        # Social bot OG tag shortcut
        if _is_social_bot(request) and _get_og_config(
            full_path, dict(request.query_params)
        ):
            return _serve_og_html(full_path, dict(request.query_params))

        file_path = (_frontend_dist / full_path).resolve()
        # Path containment: block traversal outside frontend/dist
        if not file_path.is_relative_to(_frontend_dist_resolved):
            return FileResponse(_frontend_dist / "index.html")
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(_frontend_dist / "index.html")
