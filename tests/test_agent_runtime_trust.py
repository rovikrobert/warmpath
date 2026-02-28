"""Tests for graduated trust model."""

from app.agent_runtime.trust import TrustLevel, get_allowed_tools, get_max_turns


def test_trust_level_enum_has_four_levels():
    """TrustLevel enum: observer, recommender, contributor, deployer."""
    assert TrustLevel.OBSERVER.value == 0
    assert TrustLevel.RECOMMENDER.value == 1
    assert TrustLevel.CONTRIBUTOR.value == 2
    assert TrustLevel.DEPLOYER.value == 3


def test_observer_gets_read_only_tools():
    """Trust level 0 agents can only read code."""
    tools = get_allowed_tools(TrustLevel.OBSERVER)
    assert "Read" in tools
    assert "Glob" in tools
    assert "Grep" in tools
    assert "Edit" not in tools
    assert "Write" not in tools
    assert "Bash" not in tools


def test_recommender_adds_web_tools():
    """Trust level 1 adds web search and fetch."""
    tools = get_allowed_tools(TrustLevel.RECOMMENDER)
    assert "WebSearch" in tools
    assert "WebFetch" in tools
    assert "Edit" not in tools


def test_contributor_adds_write_tools():
    """Trust level 2 adds file editing and shell access."""
    tools = get_allowed_tools(TrustLevel.CONTRIBUTOR)
    assert "Edit" in tools
    assert "Write" in tools
    assert "Bash" in tools
    assert "Task" not in tools


def test_deployer_adds_subagent_tools():
    """Trust level 3 adds ability to spawn sub-agents."""
    tools = get_allowed_tools(TrustLevel.DEPLOYER)
    assert "Task" in tools


def test_max_turns_scales_with_trust():
    """Higher trust = more turns allowed per SDK session."""
    assert get_max_turns(TrustLevel.OBSERVER) == 10
    assert get_max_turns(TrustLevel.RECOMMENDER) == 15
    assert get_max_turns(TrustLevel.CONTRIBUTOR) == 30
    assert get_max_turns(TrustLevel.DEPLOYER) == 30
