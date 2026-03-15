"""Tests for scripts/async_lint.py — async/sync misuse detector."""

import tempfile
from pathlib import Path

from scripts.async_lint import scan_file


def _scan(code: str, relpath: str = "test_file.py") -> list[dict]:
    """Write code to a temp file and scan it."""
    p = Path(tempfile.mktemp(suffix=".py"))
    try:
        p.write_text(code)
        return scan_file(p, relpath)
    finally:
        p.unlink(missing_ok=True)


class TestAsyncioRunInAsync:
    """Rule: asyncio-run-in-async — HIGH severity."""

    def test_asyncio_run_inside_async_def(self):
        findings = _scan("""
import asyncio
async def handler():
    result = asyncio.run(some_coro())
""")
        assert len(findings) == 1
        assert findings[0]["severity"] == "HIGH"
        assert findings[0]["rule"] == "asyncio-run-in-async"

    def test_asyncio_run_in_nested_async(self):
        findings = _scan("""
import asyncio
async def outer():
    async def inner():
        asyncio.run(coro())
""")
        assert len(findings) == 1
        assert findings[0]["severity"] == "HIGH"


class TestAsyncioRunWithAsyncDefs:
    """Rule: asyncio-run-with-async-defs — MEDIUM severity."""

    def test_module_level_asyncio_run_with_async_defs(self):
        findings = _scan("""
import asyncio
async def helper():
    pass
asyncio.run(helper())
""")
        assert len(findings) == 1
        assert findings[0]["severity"] == "MEDIUM"
        assert findings[0]["rule"] == "asyncio-run-with-async-defs"

    def test_asyncio_run_in_main_guard_is_clean(self):
        findings = _scan("""
import asyncio
async def main():
    pass
if __name__ == "__main__":
    asyncio.run(main())
""")
        assert len(findings) == 0

    def test_no_async_defs_is_clean(self):
        findings = _scan("""
import asyncio
def main():
    asyncio.run(some_coro())
""")
        assert len(findings) == 0


class TestSyncDbInAsync:
    """Rule: sync-db-in-async — HIGH severity."""

    def test_session_in_async_def(self):
        findings = _scan("""
from sqlalchemy.orm import Session
async def handler():
    s = Session()
""")
        assert len(findings) == 1
        assert findings[0]["rule"] == "sync-db-in-async"
        assert "Session()" in findings[0]["message"]

    def test_sessionmaker_in_async_def(self):
        findings = _scan("""
from sqlalchemy.orm import sessionmaker
async def handler():
    factory = sessionmaker()
""")
        assert len(findings) == 1
        assert findings[0]["rule"] == "sync-db-in-async"

    def test_create_engine_in_async_def(self):
        findings = _scan("""
from sqlalchemy import create_engine
async def setup():
    engine = create_engine("sqlite://")
""")
        assert len(findings) == 1
        assert findings[0]["rule"] == "sync-db-in-async"

    def test_get_sync_db_in_async_def(self):
        findings = _scan("""
from app.database import get_sync_db
async def handler():
    db = get_sync_db()
""")
        assert len(findings) == 1
        assert findings[0]["rule"] == "sync-db-in-async"

    def test_sync_session_in_sync_def_is_clean(self):
        findings = _scan("""
from sqlalchemy.orm import Session
def handler():
    s = Session()
""")
        assert len(findings) == 0


class TestAllowlists:
    """Allowlisted files should not produce findings."""

    def test_celery_task_allowlisted(self):
        findings = _scan(
            """
import asyncio
async def _helper():
    pass
def task():
    asyncio.run(_helper())
""",
            relpath="app/tasks/csv_processing.py",
        )
        assert len(findings) == 0

    def test_database_py_allowlisted(self):
        findings = _scan(
            """
from sqlalchemy.orm import sessionmaker
async def get_db():
    factory = sessionmaker()
""",
            relpath="app/database.py",
        )
        assert len(findings) == 0

    def test_non_allowlisted_file_still_flags(self):
        findings = _scan(
            """
import asyncio
async def handler():
    asyncio.run(coro())
""",
            relpath="app/api/some_route.py",
        )
        assert len(findings) == 1


class TestSyntaxErrors:
    """Files with syntax errors should be silently skipped."""

    def test_syntax_error_returns_empty(self):
        findings = _scan("def broken(:\n    pass")
        assert len(findings) == 0
