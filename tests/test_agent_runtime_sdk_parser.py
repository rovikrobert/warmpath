"""Tests for SDK output parser."""

from app.agent_runtime.sdk.parser import merge_findings, parse_sdk_output


def test_parse_sdk_output_extracts_structured_findings():
    """Parser extracts findings with all fields from SDK output."""
    messages = [
        {
            "role": "assistant",
            "content": (
                "## Finding: Unused import in auth module\n"
                "**Validated:** yes\n"
                "**Adjusted Severity:** high\n"
                "**Root Cause:** os module imported but never used\n"
                "**Proposed Fix:** Remove `import os` from app/api/auth.py line 3\n"
                "**Cross-Team Impact:** None\n"
            ),
        }
    ]
    findings = parse_sdk_output(messages, "engineering")

    assert len(findings) == 1
    f = findings[0]
    assert f["title"] == "Unused import in auth module"
    assert f["validated"] is True
    assert f["severity"] == "high"
    assert "os module" in f["root_cause"]
    assert "Remove" in f["proposed_fix"]
    assert f["source_team"] == "engineering"
    assert f["sdk_augmented"] is True


def test_parse_sdk_output_extracts_multiple_findings():
    """Parser handles multiple findings in one response."""
    messages = [
        {
            "role": "assistant",
            "content": (
                "## Finding: Missing test coverage\n"
                "**Validated:** yes\n"
                "**Adjusted Severity:** medium\n"
                "**Root Cause:** New endpoint added without tests\n"
                "**Proposed Fix:** Add test_marketplace_search.py\n"
                "**Cross-Team Impact:** Product team needs updated test plan\n"
                "\n"
                "## Finding: Stale cache entries\n"
                "**Validated:** no\n"
                "**Adjusted Severity:** low\n"
                "**Root Cause:** False positive — TTL is working correctly\n"
                "**Proposed Fix:** No fix needed\n"
                "**Cross-Team Impact:** None\n"
            ),
        }
    ]
    findings = parse_sdk_output(messages, "data")

    assert len(findings) == 2
    assert findings[0]["title"] == "Missing test coverage"
    assert findings[0]["validated"] is True
    assert findings[1]["title"] == "Stale cache entries"
    assert findings[1]["validated"] is False


def test_parse_sdk_output_returns_empty_for_no_messages():
    """Parser returns empty list when no assistant messages."""
    assert parse_sdk_output([], "engineering") == []
    assert parse_sdk_output([{"role": "system", "content": "ok"}], "ops") == []


def test_parse_sdk_output_defaults_severity_when_missing():
    """Parser defaults to medium severity when field is absent."""
    messages = [
        {
            "role": "assistant",
            "content": "## Finding: Some issue\n**Validated:** yes\n",
        }
    ]
    findings = parse_sdk_output(messages, "product")
    assert findings[0]["severity"] == "medium"


def test_merge_findings_updates_matching_scanner_finding():
    """Merge updates existing scanner finding with SDK augmentation."""
    scanner = [{"title": "Slow query", "severity": "medium", "source_team": "data"}]
    sdk = [
        {
            "title": "Slow query",
            "severity": "high",
            "root_cause": "Missing index on contacts.company",
            "sdk_augmented": True,
        }
    ]
    merged = merge_findings(scanner, sdk)

    assert len(merged) == 1
    assert merged[0]["severity"] == "high"
    assert merged[0]["root_cause"] == "Missing index on contacts.company"
    assert merged[0]["sdk_augmented"] is True
    assert merged[0]["source_team"] == "data"


def test_merge_findings_appends_new_sdk_findings():
    """Merge appends SDK findings that don't match any scanner finding."""
    scanner = [{"title": "Issue A", "severity": "low"}]
    sdk = [{"title": "Issue B", "severity": "high", "sdk_augmented": True}]
    merged = merge_findings(scanner, sdk)

    assert len(merged) == 2
    assert merged[0]["title"] == "Issue A"
    assert merged[1]["title"] == "Issue B"
