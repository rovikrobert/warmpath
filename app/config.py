from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "[DATABASE_URL_REDACTED]"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    SECURE_COOKIES: bool = False  # True in production (requires HTTPS)
    SECURE_HEADERS: bool = False  # True in production — enables HSTS
    ANTHROPIC_API_KEY: str = ""
    AI_MOCK_MODE: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CSV_ASYNC_PROCESSING: bool = True
    CORS_ORIGINS: str = "*"
    STRIPE_WEBHOOK_SECRET: str = ""
    LINKEDIN_CLIENT_ID: str = ""
    LINKEDIN_CLIENT_SECRET: str = ""
    LINKEDIN_REDIRECT_URI: str = ""
    RESEND_API_KEY: str = ""
    FROM_EMAIL: str = "WarmPath <noreply@majiq.agency>"
    FRONTEND_URL: str = "http://localhost:3000"
    ENCRYPTION_KEY: str = ""  # Fernet key (44-char base64). Empty = passthrough.
    BLIND_INDEX_KEY: str = ""  # HMAC key (hex). Empty = SHA-256 fallback.
    RATE_LIMIT_CSV_UPLOADS_PER_DAY: int = 10
    RATE_LIMIT_SEARCH_RUNS_PER_DAY: int = 50
    RATE_LIMIT_CREDIT_PURCHASES_PER_DAY: int = 5
    RATE_LIMIT_CREDIT_EXPIRE_PER_DAY: int = 2
    RECOMMENDATION_CACHE_TTL_HOURS: int = 6
    RECOMMENDATION_MAX_SCAN: int = 15
    RECOMMENDATION_MAX_RESULTS: int = 8
    DASHBOARD_TRENDS_CACHE_TTL_HOURS: int = 6
    DASHBOARD_NETWORK_CACHE_TTL_HOURS: int = 1
    KEEVS_BRIEFING_CACHE_TTL_HOURS: int = 6
    AGENT_RUN_SECRET: str = ""
    CLAUDE_MODEL: str = "claude-sonnet-4-20250514"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
