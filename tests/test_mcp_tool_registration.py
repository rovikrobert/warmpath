"""Tests for MCP tool registration — verify all 19 tools have correct names and annotations."""

import asyncio

import pytest

from mcp_server.server import mcp, register_tools

# Register all tools once at module load
register_tools()


def _list_tools():
    """Synchronously list all registered MCP tools."""
    return asyncio.run(mcp.list_tools())


@pytest.fixture(scope="module")
def all_tools():
    """Load all registered tools once for the module."""
    return {t.name: t for t in _list_tools()}


# ── Completeness ─────────────────────────────────────────────────────

EXPECTED_TOOLS = [
    "list_templates",
    "query_template",
    "query_sql",
    "get_schema",
    "check_health",
    "check_services",
    "redis_info",
    "stripe_balance",
    "stripe_subscriptions",
    "stripe_charges",
    "stripe_disputes",
    "query_audit_log",
    "enrichment_stats",
    "privacy_audit_log",
    "list_reports",
    "read_report",
    "search_memory",
    "save_memory",
    "index_session",
]


def test_all_19_tools_registered(all_tools):
    assert len(all_tools) >= 19, f"Expected >= 19 tools, got {len(all_tools)}"


@pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
def test_tool_exists(all_tools, tool_name):
    assert tool_name in all_tools, f"Tool {tool_name!r} not registered"


# ── Every tool has annotations ───────────────────────────────────────


@pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
def test_tool_has_annotations(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations is not None, f"{tool_name} missing annotations"


@pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
def test_tool_has_description(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.description, f"{tool_name} has empty description"


# ── readOnlyHint correctness ────────────────────────────────────────

WRITABLE_TOOLS = {"save_memory", "index_session"}
READ_ONLY_TOOLS = set(EXPECTED_TOOLS) - WRITABLE_TOOLS


@pytest.mark.parametrize("tool_name", sorted(READ_ONLY_TOOLS))
def test_read_only_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.readOnlyHint is True, (
        f"{tool_name} should be readOnlyHint=True"
    )


@pytest.mark.parametrize("tool_name", sorted(WRITABLE_TOOLS))
def test_writable_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.readOnlyHint is False, (
        f"{tool_name} should be readOnlyHint=False"
    )


# ── destructiveHint — all tools are non-destructive ─────────────────


@pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
def test_non_destructive(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.destructiveHint is False, (
        f"{tool_name} should be destructiveHint=False"
    )


# ── idempotentHint correctness ──────────────────────────────────────

NON_IDEMPOTENT_TOOLS = {"query_sql", "save_memory", "index_session"}
IDEMPOTENT_TOOLS = set(EXPECTED_TOOLS) - NON_IDEMPOTENT_TOOLS


@pytest.mark.parametrize("tool_name", sorted(IDEMPOTENT_TOOLS))
def test_idempotent_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.idempotentHint is True, (
        f"{tool_name} should be idempotentHint=True"
    )


@pytest.mark.parametrize("tool_name", sorted(NON_IDEMPOTENT_TOOLS))
def test_non_idempotent_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.idempotentHint is False, (
        f"{tool_name} should be idempotentHint=False"
    )


# ── openWorldHint correctness ──────────────────────────────────────

OPEN_WORLD_TOOLS = {
    "check_health",
    "stripe_balance",
    "stripe_subscriptions",
    "stripe_charges",
    "stripe_disputes",
}
CLOSED_WORLD_TOOLS = set(EXPECTED_TOOLS) - OPEN_WORLD_TOOLS


@pytest.mark.parametrize("tool_name", sorted(OPEN_WORLD_TOOLS))
def test_open_world_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.openWorldHint is True, (
        f"{tool_name} should be openWorldHint=True"
    )


@pytest.mark.parametrize("tool_name", sorted(CLOSED_WORLD_TOOLS))
def test_closed_world_tools(all_tools, tool_name):
    tool = all_tools[tool_name]
    assert tool.annotations.openWorldHint is False, (
        f"{tool_name} should be openWorldHint=False"
    )
