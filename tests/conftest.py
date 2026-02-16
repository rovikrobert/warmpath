import json
import os
import sqlite3
from collections.abc import AsyncGenerator

# Force mock mode for tests — must be set before importing app modules
os.environ["AI_MOCK_MODE"] = "true"

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import get_db
from app.main import app
from app.models import Base

# ---------------------------------------------------------------------------
# SQLite compat: teach SQLite how to render PostgreSQL-specific column types
# ---------------------------------------------------------------------------
SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: "JSON"
SQLiteTypeCompiler.visit_INET = lambda self, type_, **kw: "VARCHAR(45)"
SQLiteTypeCompiler.visit_ARRAY = lambda self, type_, **kw: "JSON"
SQLiteTypeCompiler.visit_uuid = lambda self, type_, **kw: "CHAR(36)"

# SQLite needs explicit adapters to bind/read Python lists for ARRAY→JSON columns
sqlite3.register_adapter(list, lambda val: json.dumps(val))
sqlite3.register_adapter(dict, lambda d: json.dumps(d))


# ---------------------------------------------------------------------------
# Test database setup
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
