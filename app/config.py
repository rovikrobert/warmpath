from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "[DATABASE_URL_REDACTED]"
    SECRET_KEY: str = "change-me-to-a-random-secret"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    ANTHROPIC_API_KEY: str = ""
    AI_MOCK_MODE: bool = True
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CSV_ASYNC_PROCESSING: bool = True
    CORS_ORIGINS: str = "http://localhost:3000"
    RATE_LIMIT_CSV_UPLOADS_PER_DAY: int = 10
    RATE_LIMIT_SEARCH_RUNS_PER_DAY: int = 50

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
