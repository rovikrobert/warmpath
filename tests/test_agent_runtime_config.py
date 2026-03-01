"""Tests for agent runtime configuration."""

from app.config import Settings


def test_settings_has_agent_runtime_fields():
    """Settings includes LangGraph agent runtime config with sensible defaults."""
    s = Settings()
    assert hasattr(s, "AGENT_RUNTIME_ENABLED")
    assert s.AGENT_RUNTIME_ENABLED is False
    assert hasattr(s, "AGENT_RUNTIME_BUDGET_DAILY_USD")
    assert s.AGENT_RUNTIME_BUDGET_DAILY_USD == 10.0
    assert hasattr(s, "AGENT_RUNTIME_EVENT_COOLDOWN_SECONDS")
    assert s.AGENT_RUNTIME_EVENT_COOLDOWN_SECONDS == 900
