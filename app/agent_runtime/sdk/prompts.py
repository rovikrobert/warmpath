"""Team-specific prompt templates for Claude Agent SDK augmentation sessions."""

from __future__ import annotations

from typing import Any

_TEAM_CONTEXT = {
    "engineering": "backend code quality, security, performance, and test coverage",
    "data": "data pipeline health, enrichment cache, warm score accuracy, and analytics",
    "product": "UX quality, feature completeness, onboarding flow, and user research",
    "ops": "coaching quality, marketplace health, network holder activation, and NPS",
    "gtm": "competitive positioning, pricing strategy, content pipeline, and partnerships",
    "finance": "credit economy health, burn rate, compliance, and investor readiness",
}

_SYSTEM_PROMPT = (
    "You are a senior engineering analyst for WarmPath, an AI-powered referral "
    "marketplace. You analyze scanner findings, validate them against the codebase, "
    "assess severity, identify root causes, and propose specific fixes. "
    "Be concise and actionable. Use the Read, Glob, and Grep tools to verify "
    "findings against actual code when needed."
)


def get_system_prompt() -> str:
    """Return the system prompt for SDK augmentation sessions."""
    return _SYSTEM_PROMPT


def build_augmentation_prompt(
    team: str, findings: list[dict[str, Any]], event: dict[str, Any]
) -> str:
    """Build prompt for SDK session to augment scanner findings.

    The prompt includes scanner findings and asks Claude to validate,
    assess severity, identify root causes, and propose fixes.
    """
    context = _TEAM_CONTEXT.get(team, "general platform health")
    findings_text = "\n".join(
        f"- [{f.get('severity', 'unknown')}] {f.get('title', 'Untitled')}: "
        f"{f.get('detail', 'No detail')}"
        for f in findings
    )

    return (
        f"You are analyzing findings from the {team} team scanners.\n"
        f"Team focus: {context}\n"
        f"\n"
        f"Event: {event.get('type', 'unknown')} from {event.get('source', 'unknown')}\n"
        f"\n"
        f"Scanner findings:\n{findings_text}\n"
        f"\n"
        f"For each finding:\n"
        f"1. Validate: Is this a real issue or false positive?\n"
        f"2. Assess severity: Is the scanner's severity rating accurate?\n"
        f"3. Root cause: What's the underlying issue?\n"
        f"4. Fix: Propose a specific fix with file paths and code changes.\n"
        f"5. Cross-team impact: Does this affect other teams?\n"
        f"\n"
        f"Output your analysis in this format for EACH finding:\n"
        f"## Finding: [title]\n"
        f"**Validated:** yes/no\n"
        f"**Adjusted Severity:** critical/high/medium/low\n"
        f"**Root Cause:** ...\n"
        f"**Proposed Fix:** ...\n"
        f"**Cross-Team Impact:** ...\n"
    )
