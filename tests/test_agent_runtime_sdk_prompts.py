"""Tests for SDK prompt templates."""

from app.agent_runtime.sdk.prompts import build_augmentation_prompt, get_system_prompt


def test_build_augmentation_prompt_includes_team_context():
    """Prompt includes team-specific context and findings."""
    findings = [
        {"severity": "high", "title": "Auth bypass", "detail": "Missing JWT check"}
    ]
    event = {"type": "code_change", "source": "github"}

    prompt = build_augmentation_prompt("engineering", findings, event)

    assert "engineering" in prompt
    assert "code quality" in prompt
    assert "Auth bypass" in prompt
    assert "Missing JWT check" in prompt
    assert "code_change" in prompt
    assert "github" in prompt
    assert "## Finding:" in prompt


def test_build_augmentation_prompt_handles_multiple_findings():
    """Prompt includes all findings in the list."""
    findings = [
        {"severity": "high", "title": "Issue A", "detail": "Detail A"},
        {"severity": "low", "title": "Issue B", "detail": "Detail B"},
    ]
    event = {"type": "incident", "source": "railway"}

    prompt = build_augmentation_prompt("data", findings, event)

    assert "Issue A" in prompt
    assert "Issue B" in prompt
    assert "data pipeline" in prompt


def test_build_augmentation_prompt_handles_unknown_team():
    """Prompt gracefully handles unknown team names."""
    prompt = build_augmentation_prompt(
        "unknown_team",
        [{"severity": "medium", "title": "Test", "detail": "test"}],
        {"type": "test", "source": "test"},
    )
    assert "general platform health" in prompt


def test_get_system_prompt_returns_non_empty_string():
    """System prompt is a non-empty string with key context."""
    sp = get_system_prompt()
    assert len(sp) > 50
    assert "WarmPath" in sp
    assert "scanner" in sp.lower()


def test_build_augmentation_prompt_handles_missing_fields():
    """Prompt handles findings with missing optional fields."""
    findings = [{"title": "Bare finding"}, {}]
    event = {}

    prompt = build_augmentation_prompt("ops", findings, event)

    assert "Bare finding" in prompt
    assert "unknown" in prompt  # defaults for missing severity/event fields
