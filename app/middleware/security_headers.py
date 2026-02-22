"""Security headers middleware — applies defensive headers to all responses.

Uses raw ASGI implementation (not BaseHTTPMiddleware) to avoid stacking
issues with other BaseHTTPMiddleware subclasses (e.g. UsageTrackingMiddleware).
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings

# Headers applied to every response
_ALWAYS_HEADERS: list[tuple[bytes, bytes]] = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (
        b"content-security-policy",
        b"default-src 'self';"
        b" script-src 'self' https://clerk.majiq.agency https://*.clerk.accounts.dev https://challenges.cloudflare.com;"
        b" style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;"
        b" connect-src 'self' https://clerk.majiq.agency https://*.clerk.accounts.dev https://clerk-telemetry.com;"
        b" img-src 'self' data: https://img.clerk.com;"
        b" font-src 'self' https://fonts.gstatic.com;"
        b" worker-src 'self' blob:;"
        b" frame-src 'self' https://clerk.majiq.agency https://*.clerk.accounts.dev https://challenges.cloudflare.com;",
    ),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]

# HSTS — only set when SECURE_HEADERS is enabled (production over HTTPS)
_HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")

# Cache-Control headers by path pattern
_CACHE_IMMUTABLE = b"public, max-age=31536000, immutable"
_CACHE_STATIC = b"public, max-age=3600"
_CACHE_OG_IMAGE = b"public, max-age=86400"
_CACHE_NO_CACHE = b"no-cache"


def _get_cache_control(path: str) -> bytes:
    """Return appropriate Cache-Control value based on request path."""
    if path.startswith("/assets/"):
        return _CACHE_IMMUTABLE
    if path in (
        "/robots.txt",
        "/sitemap.xml",
        "/favicon.svg",
        "/manifest.json",
    ):
        return _CACHE_STATIC
    if path == "/og-image.png":
        return _CACHE_OG_IMAGE
    # SPA HTML fallback and API routes — no cache
    return _CACHE_NO_CACHE


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "/")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_ALWAYS_HEADERS)
                if settings.SECURE_HEADERS:
                    headers.append(_HSTS_HEADER)
                headers.append((b"cache-control", _get_cache_control(path)))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
