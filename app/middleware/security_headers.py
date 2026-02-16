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
        b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:",
    ),
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]

# HSTS — only set when SECURE_HEADERS is enabled (production over HTTPS)
_HSTS_HEADER = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(_ALWAYS_HEADERS)
                if settings.SECURE_HEADERS:
                    headers.append(_HSTS_HEADER)
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
