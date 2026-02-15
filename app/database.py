from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


@lru_cache
def _get_engine():
    # Swap driver for async: postgresql:// → postgresql+asyncpg://
    url = settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    return create_async_engine(url, echo=False)


@lru_cache
def _get_session_factory():
    return async_sessionmaker(
        _get_engine(), class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _get_session_factory()() as session:
        yield session
