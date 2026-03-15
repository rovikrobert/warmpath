#!/usr/bin/env python3
"""Async/sync connection misuse detector.

Uses AST parsing to find patterns that cause runtime bugs like asyncpg
InterfaceError (PR #89):

  1. asyncio.run() inside a module that also defines async def functions
     — calling asyncio.run() inside an already-running event loop crashes
  2. Sync SQLAlchemy session usage (Session(), sessionmaker(), get_sync_db)
     inside async def functions — blocks the event loop
  3. create_engine() (sync) imported alongside async def route handlers
     — typically indicates wrong engine is being used

Exit codes: 0 = clean, 1 = findings found

Usage:
    python3 -m scripts.async_lint           # scan app/ and mcp_server/
    python3 -m scripts.async_lint --json    # JSON output
    python3 -m scripts.async_lint --verbose # show scanned file count
"""

import argparse
import ast
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = [PROJECT_ROOT / "app", PROJECT_ROOT / "mcp_server"]

# ANSI colours
RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

# ---------------------------------------------------------------------------
# Allowlists — known-safe patterns that would otherwise trigger findings
# ---------------------------------------------------------------------------

# Files where asyncio.run() coexists with async def intentionally.
# Celery tasks define async helpers then call asyncio.run() from the sync
# task wrapper — this is the correct bridge pattern.
ASYNCIO_RUN_ALLOWLIST: set[str] = {
    # Celery tasks: sync entry point calls asyncio.run() to bridge to async
    "app/tasks/csv_processing.py",
    "app/tasks/csv_pipeline.py",
    "app/tasks/vector_tasks.py",
    "app/tasks/infra_tasks.py",
    "app/tasks/agent_runtime_tasks.py",
    # CLI entrypoints
    "app/agent_runtime/__main__.py",
    "agents/memory/__main__.py",
    "scripts/backfill_company_links.py",
    "scripts/backfill_marketplace_listings.py",
    "scripts/send_founder_outreach.py",
    "scripts/migrate_users_to_clerk.py",
    "scripts/rediscover_boards.py",
    # Test helpers
    "tests/test_mcp_tool_registration.py",
    # Memory bridge: intentionally uses asyncio.run() from sync context
    "agents/shared/memory_bridge.py",
    # Railway log poller: sync entrypoint
    "app/agent_runtime/events/railway_poll.py",
}

# Files where sync Session/sessionmaker/create_engine is intentional
SYNC_SESSION_ALLOWLIST: set[str] = {
    # database.py provides both async and sync engines by design (Celery bridge)
    "app/database.py",
}

# Directories to skip entirely
SKIP_DIRS = {"__pycache__", "node_modules", ".git", "venv", ".venv", ".worktrees"}


# ---------------------------------------------------------------------------
# AST visitors
# ---------------------------------------------------------------------------


class AsyncDefCollector(ast.NodeVisitor):
    """Collect line numbers of all async def functions in a module."""

    def __init__(self) -> None:
        self.async_defs: list[tuple[str, int]] = []  # (name, lineno)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.async_defs.append((node.name, node.lineno))
        self.generic_visit(node)


class AsyncioRunFinder(ast.NodeVisitor):
    """Find asyncio.run() calls and whether they are inside async def."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, bool]] = []  # (lineno, inside_async)
        self._in_async = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        old = self._in_async
        self._in_async = True
        self.generic_visit(node)
        self._in_async = old

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_asyncio_run(node.func):
            self.calls.append((node.lineno, self._in_async))
        self.generic_visit(node)

    @staticmethod
    def _is_asyncio_run(node: ast.expr) -> bool:
        """Check if call target is asyncio.run."""
        if (
            isinstance(node, ast.Attribute)
            and node.attr == "run"
            and isinstance(node.value, ast.Name)
        ):
            return node.value.id == "asyncio"
        return False


class SyncSessionInAsyncFinder(ast.NodeVisitor):
    """Find sync SQLAlchemy session patterns inside async def functions.

    Detects:
    - Session() calls
    - sessionmaker() calls (without async_ prefix)
    - get_sync_db() calls
    - create_engine() calls (without create_async_engine)
    """

    SYNC_PATTERNS = {"Session", "sessionmaker", "get_sync_db", "create_engine"}

    def __init__(self) -> None:
        self.findings: list[tuple[int, str]] = []  # (lineno, pattern)
        self._in_async = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        old = self._in_async
        self._in_async = True
        self.generic_visit(node)
        self._in_async = old

    def visit_Call(self, node: ast.Call) -> None:
        if self._in_async:
            name = self._get_call_name(node.func)
            if name in self.SYNC_PATTERNS:
                self.findings.append((node.lineno, name))
        self.generic_visit(node)

    @staticmethod
    def _get_call_name(node: ast.expr) -> str:
        """Extract the function name from a Call node."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

Finding = dict  # {"severity", "rule", "message", "file", "line"}


def scan_file(filepath: Path, relpath: str) -> list[Finding]:
    """Scan a single Python file for async/sync misuse."""
    findings: list[Finding] = []

    try:
        source = filepath.read_text(errors="ignore")
        tree = ast.parse(source, filename=str(filepath))
    except SyntaxError:
        return findings

    # Rule 1: asyncio.run() in a module with async def
    if relpath not in ASYNCIO_RUN_ALLOWLIST:
        async_collector = AsyncDefCollector()
        async_collector.visit(tree)

        run_finder = AsyncioRunFinder()
        run_finder.visit(tree)

        if async_collector.async_defs and run_finder.calls:
            for lineno, inside_async in run_finder.calls:
                if inside_async:
                    # Worst case: asyncio.run() directly inside async def
                    findings.append(
                        {
                            "severity": "HIGH",
                            "rule": "asyncio-run-in-async",
                            "message": (
                                "asyncio.run() called inside async def — "
                                "this will raise RuntimeError in an already-running event loop"
                            ),
                            "file": relpath,
                            "line": lineno,
                        }
                    )
                else:
                    # Module-level asyncio.run() coexisting with async defs —
                    # suspicious but may be intentional (e.g. if __name__ == '__main__')
                    # Check if it is inside if __name__ == "__main__" guard
                    if not _is_in_main_guard(tree, lineno):
                        findings.append(
                            {
                                "severity": "MEDIUM",
                                "rule": "asyncio-run-with-async-defs",
                                "message": (
                                    "asyncio.run() in module that defines async functions — "
                                    "verify this is not called from an async context"
                                ),
                                "file": relpath,
                                "line": lineno,
                            }
                        )

    # Rule 2: Sync session/engine usage inside async def
    if relpath not in SYNC_SESSION_ALLOWLIST:
        sync_finder = SyncSessionInAsyncFinder()
        sync_finder.visit(tree)

        for lineno, pattern in sync_finder.findings:
            findings.append(
                {
                    "severity": "HIGH",
                    "rule": "sync-db-in-async",
                    "message": (
                        f"Sync database call `{pattern}()` inside async def — "
                        f"use async equivalent (async_sessionmaker, create_async_engine, get_db)"
                    ),
                    "file": relpath,
                    "line": lineno,
                }
            )

    return findings


def _is_in_main_guard(tree: ast.Module, target_lineno: int) -> bool:
    """Check if a given line is inside an `if __name__ == '__main__':` block."""
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            # Check for `if __name__ == "__main__"` pattern
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Eq)
            ):
                left = test.left
                right = test.comparators[0] if test.comparators else None
                if (
                    isinstance(left, ast.Name)
                    and left.id == "__name__"
                    and isinstance(right, ast.Constant)
                    and right.value == "__main__"
                ):
                    # Check if target_lineno falls within this block
                    block_start = node.lineno
                    block_end = _block_end_line(node)
                    if block_start <= target_lineno <= block_end:
                        return True
    return False


def _block_end_line(node: ast.AST) -> int:
    """Get the last line number within a node's subtree."""
    max_line = getattr(node, "lineno", 0)
    for child in ast.walk(node):
        line = getattr(child, "end_lineno", None) or getattr(child, "lineno", 0)
        if line > max_line:
            max_line = line
    return max_line


def scan_all(verbose: bool = False) -> list[Finding]:
    """Scan all Python files in configured directories."""
    all_findings: list[Finding] = []
    file_count = 0

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for py_file in sorted(scan_dir.rglob("*.py")):
            if any(skip in py_file.parts for skip in SKIP_DIRS):
                continue
            relpath = str(py_file.relative_to(PROJECT_ROOT))
            file_count += 1
            all_findings.extend(scan_file(py_file, relpath))

    if verbose:
        print(f"Scanned {file_count} files across {len(SCAN_DIRS)} directories")

    return all_findings


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def print_report(findings: list[Finding]) -> None:
    """Print human-readable findings report."""
    print(f"\n{BOLD}Async/Sync Misuse Scanner — WarmPath{RESET}")
    print(
        f"Scanning: {', '.join(str(d.relative_to(PROJECT_ROOT)) for d in SCAN_DIRS)}\n"
    )

    if not findings:
        print(f"{GREEN}{BOLD}No async/sync misuse patterns found.{RESET}\n")
        return

    for sev in ["HIGH", "MEDIUM", "LOW"]:
        sev_findings = [f for f in findings if f["severity"] == sev]
        if not sev_findings:
            continue

        color = RED if sev == "HIGH" else YELLOW if sev == "MEDIUM" else RESET
        print(f"{color}{BOLD}[{sev}] — {len(sev_findings)} finding(s){RESET}")
        for f in sev_findings:
            print(f"  {color}•{RESET} [{f['rule']}] {f['message']}")
            print(f"    {f['file']}:{f['line']}")
        print()

    total = len(findings)
    highs = sum(1 for f in findings if f["severity"] == "HIGH")
    print(f"{BOLD}Total: {total} finding(s) — {highs} high severity{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect async/sync connection misuse patterns"
    )
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--verbose", action="store_true", help="Show scan stats")
    args = parser.parse_args()

    results = scan_all(verbose=args.verbose)

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print_report(results)

    sys.exit(1 if results else 0)


if __name__ == "__main__":
    main()
