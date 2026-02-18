import json
import os
import secrets
import sqlite3
from collections.abc import AsyncGenerator

# Force mock mode for tests — must be set before importing app modules
os.environ["AI_MOCK_MODE"] = "true"
# Disable async CSV processing so uploads complete inline during tests
os.environ["CSV_ASYNC_PROCESSING"] = "false"
# Disable Resend in tests — prevents real email sends
os.environ["RESEND_API_KEY"] = ""

# Enable encryption in tests — validates the full encrypt/decrypt cycle
from cryptography.fernet import Fernet

os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["BLIND_INDEX_KEY"] = secrets.token_hex(32)

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
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
# Test database setup — create tables once, truncate between tests
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expi[RESEND_KEY_REDACTED]=False
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables once at session start, drop at session end."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(autouse=True)
async def truncate_tables():
    """Delete all rows between tests — much faster than DROP/CREATE."""
    yield
    async with engine.begin() as conn:
        # Disable FK checks for clean truncation, then re-enable
        await conn.execute(text("PRAGMA foreign_keys = OFF"))
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())
        await conn.execute(text("PRAGMA foreign_keys = ON"))


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
