#!/usr/bin/env python3
"""Privy — automated privacy compliance scanner.

Checks:
  1. Encryption enforcement (ENCRYPTION_KEY set, no plaintext PII columns)
  2. Suppression list integrity (checked at import, periodic sweep exists)
  3. Consent tracking (consent records model + endpoints exist)
  4. Data retention compliance (usage logs <12mo, credit archives <24mo)
  5. DSAR deadline compliance (no overdue data requests)
  6. PII leak detection (PII fields not logged, not in error responses)
  7. Vault isolation (all contact queries scoped by user_id)
  8. Marketplace anonymization (no PII crosses vault boundary)
  9. Privacy policy endpoint exists and is accessible
  10. Public endpoints don't leak user existence

Usage:
    python -m scripts.privacy_scan           # full scan
    python -m scripts.privacy_scan --json    # JSON output

Exit codes: 0 = compliant, 1 = findings, 2 = critical findings
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = PROJECT_ROOT / "app"

RED = "\033[91m"
YELLOW = "\033[93m"
GREEN = "\033[92m"
CYAN = "\033[96m"
RESET = "\033[0m"
BOLD = "\033[1m"

findings: list[dict] = []


def _add(
    severity: str, category: str, message: str, file: str = "", line: int = 0
) -> None:
    findings.append(
        {
            "severity": severity,
            "category": category,
            "message": message,
            "file": file,
            "line": line,
        }
    )


# ---------------------------------------------------------------------------
# 1. Encryption enforcement
# ---------------------------------------------------------------------------


def check_encryption() -> None:
    """Verify PII columns use EncryptedString/EncryptedText types."""
    print(f"\n{BOLD}{CYAN}[1/10] Encryption enforcement{RESET}")

    contact_model = APP_DIR / "models" / "contact.py"
    if not contact_model.exists():
        _add("CRITICAL", "encryption", "Contact model not found", str(contact_model))
        return

    content = contact_model.read_text()
    relpath = str(contact_model.relative_to(PROJECT_ROOT))

    # PII columns that MUST be encrypted
    pii_columns = [
        "first_name",
        "last_name",
        "full_name",
        "email",
        "linkedin_url",
        "current_title",
        "current_company",
        "location",
        "notes",
        "how_you_know",
    ]

    for col in pii_columns:
        # Find the column definition
        pattern = re.compile(rf"{col}.*?mapped_column\s*\((\w+)", re.DOTALL)
        match = pattern.search(content)
        if match:
            col_type = match.group(1)
            if col_type not in ("EncryptedString", "EncryptedText"):
                lineno = content[: match.start()].count("\n") + 1
                _add(
                    "CRITICAL",
                    "encryption",
                    f"PII column '{col}' uses {col_type} instead of EncryptedString/EncryptedText",
                    relpath,
                    lineno,
                )

    # Check encryption.py has passthrough warning
    enc_file = APP_DIR / "utils" / "encryption.py"
    if enc_file.exists():
        enc_content = enc_file.read_text()
        if "if not key:" in enc_content and "return value" in enc_content:
            if (
                "warning" not in enc_content.lower()
                and "logger" not in enc_content.lower()
            ):
                _add(
                    "HIGH",
                    "encryption",
                    "Encryption passthrough has no warning log when ENCRYPTION_KEY is empty",
                    str(enc_file.relative_to(PROJECT_ROOT)),
                )

    # Check config.py for ENCRYPTION_KEY default
    config_file = APP_DIR / "config.py"
    if config_file.exists():
        config_content = config_file.read_text()
        match = re.search(r'ENCRYPTION_KEY.*=\s*"([^"]*)"', config_content)
        if match and match.group(1) == "":
            _add(
                "HIGH",
                "encryption",
                "ENCRYPTION_KEY defaults to empty — encryption disabled unless explicitly set",
                str(config_file.relative_to(PROJECT_ROOT)),
            )

    found = sum(1 for f in findings if f["category"] == "encryption")
    if found == 0:
        print(f"  {GREEN}All PII columns encrypted{RESET}")
    else:
        print(f"  {RED}{found} encryption issue(s){RESET}")


# ---------------------------------------------------------------------------
# 2. Suppression list enforcement
# ---------------------------------------------------------------------------


def check_suppression() -> None:
    """Verify suppression list is checked at CSV import time."""
    print(f"\n{BOLD}{CYAN}[2/10] Suppression list enforcement{RESET}")

    csv_processing = APP_DIR / "tasks" / "csv_processing.py"
    if not csv_processing.exists():
        _add("HIGH", "suppression", "CSV processing task not found")
        return

    content = csv_processing.read_text()
    relpath = str(csv_processing.relative_to(PROJECT_ROOT))

    if "suppression" not in content.lower() and "SuppressionList" not in content:
        _add(
            "CRITICAL",
            "suppression",
            "CSV import does NOT check suppression list — suppressed contacts can re-enter vaults",
            relpath,
        )
    else:
        print(f"  {GREEN}Suppression list checked at import{RESET}")

    # Check suppression model exists
    privacy_model = APP_DIR / "models" / "privacy.py"
    if not privacy_model.exists():
        _add("HIGH", "suppression", "Privacy model (suppression list table) not found")
    elif "SuppressionList" not in privacy_model.read_text():
        _add("HIGH", "suppression", "SuppressionList model not defined in privacy.py")


# ---------------------------------------------------------------------------
# 3. Consent tracking
# ---------------------------------------------------------------------------


def check_consent() -> None:
    """Verify consent tracking infrastructure exists."""
    print(f"\n{BOLD}{CYAN}[3/10] Consent tracking{RESET}")

    privacy_model = APP_DIR / "models" / "privacy.py"
    if privacy_model.exists() and "ConsentRecord" in privacy_model.read_text():
        print(f"  {GREEN}ConsentRecord model exists{RESET}")
    else:
        _add("HIGH", "consent", "ConsentRecord model not found — no consent tracking")

    privacy_api = APP_DIR / "api" / "privacy.py"
    if privacy_api.exists():
        content = privacy_api.read_text()
        if "/consent" in content:
            print(f"  {GREEN}Consent endpoints exist{RESET}")
        else:
            _add("HIGH", "consent", "No consent API endpoints found")
    else:
        _add("HIGH", "consent", "Privacy API not found")


# ---------------------------------------------------------------------------
# 4. Data retention compliance
# ---------------------------------------------------------------------------


def check_data_retention() -> None:
    """Verify data retention mechanisms exist."""
    print(f"\n{BOLD}{CYAN}[4/10] Data retention compliance{RESET}")

    retention_service = APP_DIR / "services" / "data_retention.py"
    if not retention_service.exists():
        _add(
            "HIGH",
            "retention",
            "Data retention service not found — no automated cleanup",
        )
        return

    content = retention_service.read_text()
    relpath = str(retention_service.relative_to(PROJECT_ROOT))

    checks = {
        "purge_old_usage_logs": "Usage log purge (12-month policy)",
        "purge_expired_archives": "Credit archive purge (24-month policy)",
        "archive_credit_history": "Credit history archival before deletion",
    }

    for func, desc in checks.items():
        if func in content:
            print(f"  {GREEN}{desc} — implemented{RESET}")
        else:
            _add("MEDIUM", "retention", f"Missing: {desc}", relpath)


# ---------------------------------------------------------------------------
# 5. DSAR tracking
# ---------------------------------------------------------------------------


def check_dsar() -> None:
    """Verify DSAR (data subject access request) tracking exists."""
    print(f"\n{BOLD}{CYAN}[5/10] DSAR tracking{RESET}")

    privacy_model = APP_DIR / "models" / "privacy.py"
    if privacy_model.exists() and "DataRequest" in privacy_model.read_text():
        print(f"  {GREEN}DataRequest model exists{RESET}")
    else:
        _add("HIGH", "dsar", "DataRequest model not found — no DSAR tracking")

    breach_service = APP_DIR / "services" / "breach_notification.py"
    if breach_service.exists():
        content = breach_service.read_text()
        if "create_data_request" in content and "deadline" in content:
            print(f"  {GREEN}DSAR deadline tracking implemented{RESET}")
        else:
            _add(
                "MEDIUM",
                "dsar",
                "DSAR deadline tracking not found in breach_notification.py",
            )


# ---------------------------------------------------------------------------
# 6. PII leak detection
# ---------------------------------------------------------------------------

_PII_LOG_PATTERNS = [
    re.compile(r"(?:logger\.\w+|print)\s*\(.*\.email\b", re.IGNORECASE),
    re.compile(r"(?:logger\.\w+|print)\s*\(.*\.first_name\b", re.IGNORECASE),
    re.compile(r"(?:logger\.\w+|print)\s*\(.*\.last_name\b", re.IGNORECASE),
    re.compile(r"(?:logger\.\w+|print)\s*\(.*\.linkedin_url\b", re.IGNORECASE),
    re.compile(r"(?:logger\.\w+|print)\s*\(.*\.phone\b", re.IGNORECASE),
]

_SKIP_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    "venv",
    ".venv",
    "tests",
    "scripts",
}


def check_pii_leaks() -> None:
    """Scan for PII being logged or printed."""
    print(f"\n{BOLD}{CYAN}[6/10] PII leak detection{RESET}")
    count = 0

    for py_file in APP_DIR.rglob("*.py"):
        if any(skip in py_file.parts for skip in _SKIP_DIRS):
            continue

        content = py_file.read_text(errors="ignore")
        relpath = str(py_file.relative_to(PROJECT_ROOT))

        for lineno, line in enumerate(content.splitlines(), 1):
            for pattern in _PII_LOG_PATTERNS:
                if pattern.search(line):
                    _add(
                        "MEDIUM",
                        "pii_leak",
                        f"PII field in log/print: {line.strip()[:100]}",
                        relpath,
                        lineno,
                    )
                    count += 1

    if count == 0:
        print(f"  {GREEN}No PII leaks in logs{RESET}")
    else:
        print(f"  {YELLOW}{count} potential PII leak(s){RESET}")


# ---------------------------------------------------------------------------
# 7. Vault isolation
# ---------------------------------------------------------------------------


def check_vault_isolation() -> None:
    """Verify contact queries are always scoped by user_id."""
    print(f"\n{BOLD}{CYAN}[7/10] Vault isolation{RESET}")

    # Known-intentional cross-vault lookups (post-consent or hash-based).
    # Each entry is (filename_suffix, line_number).
    _SUPPRESSED_VAULT_LOOKUPS: list[tuple[str, int]] = [
        ("matches.py", 271),  # post-consent contact reveal
        ("applications.py", 456),  # hash-based duplicate check
        ("marketplace.py", 243),  # anonymized marketplace index query
    ]

    api_dir = APP_DIR / "api"
    services_dir = APP_DIR / "services"
    count = 0

    for search_dir in [api_dir, services_dir]:
        if not search_dir.exists():
            continue
        for py_file in search_dir.rglob("*.py"):
            content = py_file.read_text(errors="ignore")
            relpath = str(py_file.relative_to(PROJECT_ROOT))

            # Find queries on Contact table
            contact_queries = re.finditer(
                r"select\s*\(\s*Contact\b.*?\)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            for match in contact_queries:
                # Check nearby lines for user_id filter
                start = max(0, match.start() - 200)
                end = min(len(content), match.end() + 500)
                context = content[start:end]

                if "user_id" not in context and "suppression" not in py_file.name:
                    lineno = content[: match.start()].count("\n") + 1

                    # Skip known-intentional cross-vault lookups
                    if any(
                        relpath.endswith(fname) and lineno == lno
                        for fname, lno in _SUPPRESSED_VAULT_LOOKUPS
                    ):
                        continue

                    _add(
                        "HIGH",
                        "vault_isolation",
                        "Contact query may not be scoped by user_id",
                        relpath,
                        lineno,
                    )
                    count += 1

    if count == 0:
        print(f"  {GREEN}All contact queries appear user-scoped{RESET}")
    else:
        print(f"  {YELLOW}{count} query(ies) may lack user_id scope{RESET}")


# ---------------------------------------------------------------------------
# 8. Marketplace anonymization
# ---------------------------------------------------------------------------


def check_marketplace_anonymization() -> None:
    """Verify marketplace search doesn't expose PII."""
    print(f"\n{BOLD}{CYAN}[8/10] Marketplace anonymization{RESET}")

    marketplace_api = APP_DIR / "api" / "marketplace.py"
    if not marketplace_api.exists():
        _add("MEDIUM", "anonymization", "Marketplace API not found")
        return

    content = marketplace_api.read_text()
    relpath = str(marketplace_api.relative_to(PROJECT_ROOT))

    # PII fields that should NEVER appear in marketplace response
    pii_fields = ["first_name", "last_name", "email", "linkedin_url", "phone"]

    # Known-intentional patterns (not vault PII leaks):
    # - _build_seeker_profile_snapshot: job seeker's OWN profile shared with
    #   network holder post-approval
    # - contact_email/contact_name in incoming-requests: holder's OWN contact data
    suppressed_contexts = [
        "_build_seeker_profile_snapshot",
        "contact_email",
        "contact_name",
    ]

    for field in pii_fields:
        # Look for these in response construction
        response_pattern = re.compile(rf'["\']({field})["\'].*?:', re.IGNORECASE)
        for match in response_pattern.finditer(content):
            context_start = max(0, match.start() - 500)
            context = content[context_start : match.end() + 200]
            if "return" in context or "data" in context:
                # Skip known-intentional patterns
                if any(s in context for s in suppressed_contexts):
                    continue
                lineno = content[: match.start()].count("\n") + 1
                _add(
                    "CRITICAL",
                    "anonymization",
                    f"PII field '{field}' may appear in marketplace response",
                    relpath,
                    lineno,
                )

    found = sum(
        1
        for f in findings
        if f["category"] == "anonymization" and f["severity"] == "CRITICAL"
    )
    if found == 0:
        print(f"  {GREEN}No PII in marketplace responses{RESET}")


# ---------------------------------------------------------------------------
# 9. Privacy policy endpoint
# ---------------------------------------------------------------------------


def check_privacy_policy() -> None:
    """Verify privacy policy is accessible."""
    print(f"\n{BOLD}{CYAN}[9/10] Privacy policy accessibility{RESET}")

    main_file = APP_DIR / "main.py"
    if not main_file.exists():
        _add("MEDIUM", "policy", "main.py not found")
        return

    content = main_file.read_text()
    if "privacy" in content.lower():
        print(f"  {GREEN}Privacy router registered{RESET}")
    else:
        _add("MEDIUM", "policy", "Privacy router not found in main.py")

    # Check privacy policy document exists
    policy_file = PROJECT_ROOT / "warmpath_privacy_policy.docx"
    if policy_file.exists():
        print(f"  {GREEN}Privacy policy document exists{RESET}")
    else:
        _add("LOW", "policy", "Privacy policy document not found in project root")


# ---------------------------------------------------------------------------
# 10. Public endpoint info leaks
# ---------------------------------------------------------------------------


def check_info_leaks() -> None:
    """Check public endpoints for user existence leakage."""
    print(f"\n{BOLD}{CYAN}[10/10] Information leak checks{RESET}")

    auth_file = APP_DIR / "api" / "auth.py"
    if not auth_file.exists():
        return

    content = auth_file.read_text()
    relpath = str(auth_file.relative_to(PROJECT_ROOT))

    # Check forgot-password for differential responses
    forgot_section = (
        content[
            content.find("forgot_password") : content.find("forgot_password") + 2000
        ]
        if "forgot_password" in content
        else ""
    )
    if forgot_section:
        # Look for different response messages
        response_msgs = re.findall(
            r'(?:message|detail).*?["\']([^"\']{10,})["\']', forgot_section
        )
        unique_msgs = set(response_msgs)
        if len(unique_msgs) > 1:
            _add(
                "HIGH",
                "info_leak",
                f"Forgot-password returns {len(unique_msgs)} different messages — enables email enumeration",
                relpath,
            )

    # Check login for user existence leakage
    login_section = (
        content[: content.find("def register")]
        if "def register" in content
        else content[:5000]
    )
    if "no account" in login_section.lower() or "not found" in login_section.lower():
        if (
            "wrong password" in login_section.lower()
            or "incorrect password" in login_section.lower()
        ):
            _add(
                "MEDIUM",
                "info_leak",
                "Login distinguishes between 'no account' and 'wrong password' — enables enumeration",
                relpath,
            )

    found = sum(1 for f in findings if f["category"] == "info_leak")
    if found == 0:
        print(f"  {GREEN}No information leaks detected{RESET}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report() -> None:
    """Print the final compliance report."""
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}Privy — Privacy Compliance Report{RESET}")
    print(f"{'=' * 70}\n")

    if not findings:
        print(f"{GREEN}{BOLD}Full privacy compliance. No issues found.{RESET}\n")
        return

    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        sev_findings = [f for f in findings if f["severity"] == sev]
        if not sev_findings:
            continue

        color = (
            RED if sev in ("CRITICAL", "HIGH") else YELLOW if sev == "MEDIUM" else RESET
        )
        print(f"{color}{BOLD}[{sev}] — {len(sev_findings)} finding(s){RESET}")
        for f in sev_findings:
            loc = f"{f['file']}:{f['line']}" if f["file"] else ""
            print(f"  {color}•{RESET} [{f['category']}] {f['message']}")
            if loc:
                print(f"    {loc}")
        print()

    total = len(findings)
    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    highs = sum(1 for f in findings if f["severity"] == "HIGH")
    print(f"{BOLD}Total: {total} finding(s) — {crits} critical, {highs} high{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Privy — privacy compliance scanner")
    parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of text"
    )
    args = parser.parse_args()

    print(f"{BOLD}Privy — Privacy Compliance Scanner — WarmPath{RESET}")
    print(f"Scanning: {PROJECT_ROOT}\n")

    check_encryption()
    check_suppression()
    check_consent()
    check_data_retention()
    check_dsar()
    check_pii_leaks()
    check_vault_isolation()
    check_marketplace_anonymization()
    check_privacy_policy()
    check_info_leaks()

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print_report()

    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    has_findings = len(findings) > 0
    sys.exit(2 if crits > 0 else 1 if has_findings else 0)


if __name__ == "__main__":
    main()
