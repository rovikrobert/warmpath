"""Parse Claude Agent SDK session output into structured findings."""

from __future__ import annotations

import re
from typing import Any


def parse_sdk_output(messages: list[dict[str, str]], team: str) -> list[dict[str, Any]]:
    """Parse SDK session messages into Finding-compatible dicts.

    Extracts structured sections from the last assistant message:
    ## Finding: [title]
    **Validated:** yes/no
    **Adjusted Severity:** critical/high/medium/low
    **Root Cause:** ...
    **Proposed Fix:** ...
    **Cross-Team Impact:** ...
    """
    # Collect all assistant text
    text = "\n".join(m["content"] for m in messages if m.get("role") == "assistant")
    if not text:
        return []

    return _extract_findings(text, team)


_FINDING_PATTERN = re.compile(r"##\s*Finding:\s*(.+?)(?=\n##\s*Finding:|\Z)", re.DOTALL)

_FIELD_PATTERNS = {
    "validated": re.compile(r"\*\*Validated:\*\*\s*(yes|no)", re.IGNORECASE),
    "severity": re.compile(
        r"\*\*Adjusted Severity:\*\*\s*(critical|high|medium|low)", re.IGNORECASE
    ),
    "root_cause": re.compile(r"\*\*Root Cause:\*\*\s*(.+?)(?=\n\*\*|\Z)", re.DOTALL),
    "proposed_fix": re.compile(
        r"\*\*Proposed Fix:\*\*\s*(.+?)(?=\n\*\*|\Z)", re.DOTALL
    ),
    "cross_team_impact": re.compile(
        r"\*\*Cross-Team Impact:\*\*\s*(.+?)(?=\n\*\*|\n##|\Z)", re.DOTALL
    ),
}


def _extract_findings(text: str, team: str) -> list[dict[str, Any]]:
    """Extract individual findings from SDK output text."""
    findings: list[dict[str, Any]] = []

    for match in _FINDING_PATTERN.finditer(text):
        block = match.group(0)
        title_line = match.group(1).strip().split("\n")[0].strip()

        finding: dict[str, Any] = {
            "title": title_line,
            "source_team": team,
            "sdk_augmented": True,
        }

        for field, pattern in _FIELD_PATTERNS.items():
            field_match = pattern.search(block)
            if field_match:
                finding[field] = field_match.group(1).strip()

        # Normalize validated to bool
        if "validated" in finding:
            finding["validated"] = finding["validated"].lower() == "yes"

        # Default severity if not found
        if "severity" not in finding:
            finding["severity"] = "medium"

        findings.append(finding)

    return findings


def merge_findings(
    scanner_findings: list[dict[str, Any]],
    sdk_findings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge scanner findings with SDK augmentation results.

    SDK findings that match a scanner finding by title update it in place.
    SDK findings that don't match are appended as new findings.
    """
    merged = list(scanner_findings)
    scanner_titles = {f.get("title", "").lower(): i for i, f in enumerate(merged)}

    for sdk_f in sdk_findings:
        title_key = sdk_f.get("title", "").lower()
        if title_key in scanner_titles:
            idx = scanner_titles[title_key]
            merged[idx].update(
                {k: v for k, v in sdk_f.items() if k != "title" and v is not None}
            )
        else:
            merged.append(sdk_f)

    return merged
