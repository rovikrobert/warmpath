from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "[DATABASE_URL_REDACTED]"
    SECURE_HEADERS: bool = False  # True in production — enables HSTS
    ANTHROPIC_API_KEY: str = ""
    AI_MOCK_MODE: bool = True
    BETA_SANDBOX_MODE: bool = True  # Relaxed limits for early beta users
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CSV_ASYNC_PROCESSING: bool = True
    CORS_ORIGINS: str = "http://localhost:5173"
    STRIPE_WEBHOOK_SECRET: str = ""
    CLERK_SECRET_KEY: str = ""
    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_WEBHOOK_SECRET: str = ""
    CLERK_DOMAIN: str = ""  # e.g. "your-app.clerk.accounts.dev"
    RESEND_API_KEY: str = ""
    RESEND_WEBHOOK_SECRET: str = ""
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
    CLAUDE_SCORER_MODEL: str = "claude-haiku-4-5-20251001"
    # Scaling settings
    SERVICE_ROLE: str = "all"  # web | worker | beat | all
    CELERY_CONCURRENCY: int = 2
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    ANTHROPIC_MAX_CONCURRENT: int = 5
    GOOGLE_API_KEY: str = ""
    GOOGLE_PROJECT_ID: str = ""  # GCP project for Vertex AI
    GOOGLE_LOCATION: str = "us-central1"  # Vertex AI region
    GOOGLE_SERVICE_ACCOUNT_JSON: str = ""  # SA key JSON (enables Vertex AI)
    GOOGLE_MAX_CONCURRENT: int = 10
    OPENAI_API_KEY: str = ""
    OPENAI_MAX_CONCURRENT: int = 10
    GROQ_API_KEY: str = ""
    GROQ_MAX_CONCURRENT: int = 30
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_MAX_CONCURRENT: int = 10
    # Pipeline v2 settings
    CSV_PIPELINE_V2: bool = False  # Feature flag: True = streaming pipeline
    CSV_CHUNK_SIZE: int = 500  # contacts per AI batch
    CSV_STREAM_TTL_SECONDS: int = 3600  # 1 hour TTL for Redis Streams
    CLEANUP_PROVIDER: str = "gemini"  # "anthropic" | "gemini"
    QUEUE_DEPTH_THRESHOLD: int = 20
    ADZUNA_APP_ID: str = ""
    ADZUNA_APP_KEY: str = ""
    JOBSPY_ENABLED: bool = True
    JOBSPY_SEARCH_ALL_SITES: bool = True
    POSTHOG_API_KEY: str = ""
    POSTHOG_PROJECT_ID: str = ""
    POSTHOG_HOST: str = "https://app.posthog.com"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
