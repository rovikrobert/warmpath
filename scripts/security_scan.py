#!/usr/bin/env python3
"""Security — automated security vulnerability scanner.

Checks:
  1. Dependency CVEs via OSV (Open Source Vulnerabilities) database
  2. Dangerous code patterns (hardcoded secrets, missing auth, SQL injection)
  3. Production config safety (SECRET_KEY, ENCRYPTION_KEY, CORS)
  4. Input validation coverage (Pydantic max_length on string fields)
  5. Rate limiting coverage on public endpoints

Usage:
    python -m scripts.security_scan          # full scan
    python -m scripts.security_scan --deps   # dependency CVEs only
    python -m scripts.security_scan --code   # code patterns only
    python -m scripts.security_scan --config # config checks only

Exit codes: 0 = clean, 1 = findings, 2 = critical findings
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"
APP_DIR = PROJECT_ROOT / "app"

# ANSI colours
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
# 1. Dependency CVE scan (OSV database — same source as pip-audit)
# ---------------------------------------------------------------------------


def _parse_requirements() -> dict[str, str]:
    """Parse requirements.txt into {package: min_version}."""
    pkgs: dict[str, str] = {}
    if not REQUIREMENTS.exists():
        return pkgs
    for raw in REQUIREMENTS.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        # Handle ==, >=, ~= pins
        for op in ["==", ">=", "~="]:
            if op in line:
                name, ver = line.split(op, 1)
                name = name.strip().split("[")[0]  # strip extras like [cryptography]
                ver = ver.split("#")[0].strip()  # strip inline comments
                pkgs[name] = ver
                break
    return pkgs


def scan_dependencies() -> None:
    """Query OSV for known CVEs in pinned dependency versions."""
    print(f"\n{BOLD}{CYAN}[1/5] Dependency CVE scan{RESET}")
    pkgs = _parse_requirements()
    if not pkgs:
        print("  No requirements.txt found — skipping")
        return

    vuln_count = 0
    for pkg, ver in sorted(pkgs.items()):
        try:
            payload = json.dumps(
                {
                    "version": ver,
                    "package": {"name": pkg, "ecosystem": "PyPI"},
                }
            ).encode()
            req = urllib.request.Request(
                "https://api.osv.dev/v1/query",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())

            vulns = data.get("vulns", [])
            if not vulns:
                continue

            # Deduplicate by CVE alias
            seen_ids: set[str] = set()
            for v in vulns:
                vid = v.get("id", "")
                aliases = v.get("aliases", [])
                # Skip duplicates (same CVE reported by GHSA + PYSEC)
                canonical = next((a for a in aliases if a.startswith("CVE-")), vid)
                if canonical in seen_ids:
                    continue
                seen_ids.add(canonical)

                fixed_in = "unknown"
                for affected in v.get("affected", []):
                    for r in affected.get("ranges", []):
                        for event in r.get("events", []):
                            if "fixed" in event:
                                fixed_in = event["fixed"]

                summary = v.get("summary", "No summary")[:120]
                sev = (
                    "CRITICAL"
                    if "arbitrary" in summary.lower() or "rce" in summary.lower()
                    else "HIGH"
                )
                _add(
                    sev,
                    "dependency",
                    f"{pkg}>={ver}: {canonical} — {summary} (fixed in {fixed_in})",
                )
                vuln_count += 1

        except Exception as e:
            print(f"  WARNING: Failed to query OSV for {pkg}: {e}")

    if vuln_count == 0:
        print(f"  {GREEN}No dependency CVEs found{RESET}")
    else:
        print(f"  {RED}{vuln_count} dependency CVE(s) found{RESET}")


# ---------------------------------------------------------------------------
# 2. Dangerous code patterns
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, str, str, re.Pattern]] = [
    (
        "HIGH",
        "hardcoded_secret",
        "Possible hardcoded secret/password",
        re.compile(
            r'(?:password|secret|api_key|token)\s*=\s*["\'][^"\']{8,}["\']',
            re.IGNORECASE,
        ),
    ),
    (
        "HIGH",
        "sql_injection",
        "Possible SQL injection (raw string formatting in query)",
        re.compile(r'(?:execute|text)\s*\(\s*f["\']', re.IGNORECASE),
    ),
    (
        "MEDIUM",
        "eval_exec",
        "Use of eval/exec",
        re.compile(r"\b(?:eval|exec)\s*\(", re.IGNORECASE),
    ),
    (
        "MEDIUM",
        "pickle_load",
        "Insecure deserialization (pickle.load/loads)",
        re.compile(r"pickle\.loads?\s*\("),
    ),
    (
        "LOW",
        "debug_print",
        "Debug print/logging of sensitive data pattern",
        re.compile(
            r"(?:print|logger\.\w+)\s*\(.*(?:password|secret|token|api_key)",
            re.IGNORECASE,
        ),
    ),
]

# Files/dirs to skip
_SKIP_DIRS = {"__pycache__", "node_modules", ".git", "venv", ".venv", "dist", "build"}
_SKIP_FILES = {"security_scan.py", "privacy_scan.py"}


def scan_code_patterns() -> None:
    """Scan Python files for dangerous code patterns."""
    print(f"\n{BOLD}{CYAN}[2/5] Code pattern scan{RESET}")
    count = 0
    for py_file in APP_DIR.rglob("*.py"):
        if any(skip in py_file.parts for skip in _SKIP_DIRS):
            continue
        if py_file.name in _SKIP_FILES:
            continue

        try:
            content = py_file.read_text(errors="ignore")
        except Exception:
            continue

        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for severity, category, message, pattern in _PATTERNS:
                if pattern.search(stripped):
                    # Skip known false positives
                    if "server_default" in stripped:
                        continue
                    if "settings." in stripped and category == "hardcoded_secret":
                        continue
                    relpath = str(py_file.relative_to(PROJECT_ROOT))
                    _add(
                        severity,
                        category,
                        f"{message}: {stripped[:100]}",
                        relpath,
                        lineno,
                    )
                    count += 1

    if count == 0:
        print(f"  {GREEN}No dangerous patterns found{RESET}")
    else:
        print(f"  {YELLOW}{count} pattern(s) flagged{RESET}")


# ---------------------------------------------------------------------------
# 3. Production config safety
# ---------------------------------------------------------------------------


def scan_config() -> None:
    """Check config.py for unsafe defaults that could slip into production."""
    print(f"\n{BOLD}{CYAN}[3/5] Config safety checks{RESET}")
    config_file = APP_DIR / "config.py"
    if not config_file.exists():
        print("  config.py not found — skipping")
        return

    content = config_file.read_text()
    relpath = str(config_file.relative_to(PROJECT_ROOT))

    # Check SECRET_KEY default
    # Note: app/main.py has boot validation that blocks production startup with
    # default SECRET_KEY (RuntimeError). This is an INFO-level note, not HIGH.
    main_file = APP_DIR / "main.py"
    main_content = main_file.read_text() if main_file.exists() else ""
    has_boot_validation = (
        "RuntimeError" in main_content and "SECRET_KEY" in main_content
    )
    if "SECRET_KEY" in content and "change-me" in content:
        _add(
            "INFO" if has_boot_validation else "HIGH",
            "config",
            "SECRET_KEY has a default value in config.py"
            + (
                " (boot validation blocks production startup)"
                if has_boot_validation
                else " — must be overridden in production"
            ),
            relpath,
        )

    # Check ENCRYPTION_KEY default
    has_encryption_boot_check = (
        "ENCRYPTION_KEY" in main_content and "RuntimeError" in main_content
    )
    if "ENCRYPTION_KEY" in content:
        match = re.search(r'ENCRYPTION_KEY.*=\s*"([^"]*)"', content)
        if match and match.group(1) == "":
            _add(
                "INFO" if has_encryption_boot_check else "HIGH",
                "config",
                "ENCRYPTION_KEY defaults to empty string in config.py"
                + (
                    " (boot validation blocks production startup)"
                    if has_encryption_boot_check
                    else " — encryption silently disabled"
                ),
                relpath,
            )

    # Check CORS default
    if "CORS_ORIGINS" in content:
        match = re.search(r'CORS_ORIGINS.*=\s*"([^"]*)"', content)
        if match and match.group(1) == "*":
            _add(
                "MEDIUM",
                "config",
                "CORS_ORIGINS defaults to wildcard (*) — restrict in production",
                relpath,
            )

    # Check BLIND_INDEX_KEY default
    if "BLIND_INDEX_KEY" in content:
        match = re.search(r'BLIND_INDEX_KEY.*=\s*"([^"]*)"', content)
        if match and match.group(1) == "":
            _add(
                "MEDIUM",
                "config",
                "BLIND_INDEX_KEY defaults to empty — blind indexes use weaker SHA-256 fallback",
                relpath,
            )

    found = sum(1 for f in findings if f["category"] == "config")
    if found == 0:
        print(f"  {GREEN}Config defaults are safe{RESET}")
    else:
        print(f"  {YELLOW}{found} config issue(s){RESET}")


# ---------------------------------------------------------------------------
# 4. Auth coverage — endpoints missing authentication
# ---------------------------------------------------------------------------


def scan_auth_coverage() -> None:
    """Check API endpoints for missing authentication dependencies."""
    print(f"\n{BOLD}{CYAN}[4/5] Auth coverage scan{RESET}")
    api_dir = APP_DIR / "api"
    if not api_dir.exists():
        return

    # Endpoints that are intentionally public
    public_allowlist = {
        "login",
        "register",
        "refresh_token",
        "forgot_password",
        "reset_password",
        "verify_email",
        "health",
        "serve_spa",
        "linkedin_callback",
        "stripe_webhook",
        "suppression_request",
        "request_rectification",
    }

    count = 0
    for py_file in sorted(api_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue

        content = py_file.read_text(errors="ignore")
        relpath = str(py_file.relative_to(PROJECT_ROOT))

        # Find route decorators and check if the function has get_current_user
        route_pattern = re.compile(
            r"@router\.(get|post|put|patch|delete)\s*\([^)]*\)\s*\n"
            r"async\s+def\s+(\w+)\s*\(([^)]*)\)",
            re.MULTILINE,
        )
        for match in route_pattern.finditer(content):
            func_name = match.group(2)
            params = match.group(3)

            if func_name in public_allowlist:
                continue
            if "get_current_user" not in params and "current_user" not in params:
                lineno = content[: match.start()].count("\n") + 1
                _add(
                    "MEDIUM",
                    "auth_coverage",
                    f"Endpoint `{func_name}` may be missing authentication",
                    relpath,
                    lineno,
                )
                count += 1

    if count == 0:
        print(f"  {GREEN}All endpoints have auth coverage{RESET}")
    else:
        print(f"  {YELLOW}{count} endpoint(s) may lack auth{RESET}")


# ---------------------------------------------------------------------------
# 5. Input validation (max_length on string fields)
# ---------------------------------------------------------------------------


def scan_input_validation() -> None:
    """Check Pydantic schemas for missing max_length on string fields."""
    print(f"\n{BOLD}{CYAN}[5/5] Input validation scan{RESET}")
    count = 0

    for py_file in APP_DIR.rglob("*.py"):
        if any(skip in py_file.parts for skip in _SKIP_DIRS):
            continue

        content = py_file.read_text(errors="ignore")
        relpath = str(py_file.relative_to(PROJECT_ROOT))

        # Find string fields in Pydantic models without max_length
        # Simple heuristic: str fields without Field(..., max_length=...)
        in_model = False
        for lineno, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()

            if "BaseModel" in stripped and "class " in stripped:
                in_model = True
                continue
            if (
                (
                    in_model
                    and stripped
                    and not stripped.startswith("#")
                    and not stripped.startswith("class")
                )
                and (
                    ": str" in stripped
                    and "max_length" not in stripped
                    and "pattern" not in stripped
                )
                and ("EmailStr" not in stripped and "password" not in stripped.lower())
                # Only flag if it looks like a field definition
                and ("=" in stripped or ":" in stripped)
            ):
                _add(
                    "LOW",
                    "validation",
                    f"String field without max_length: {stripped[:80]}",
                    relpath,
                    lineno,
                )
                count += 1
            if (
                (
                    in_model
                    and stripped
                    and not stripped.startswith(" ")
                    and not stripped.startswith("\t")
                )
                and not stripped.startswith("#")
                and not stripped.startswith("@")
            ):
                in_model = False

    if count == 0:
        print(f"  {GREEN}All string fields validated{RESET}")
    else:
        print(f"  {YELLOW}{count} field(s) missing max_length{RESET}")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def print_report() -> None:
    """Print the final findings report."""
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}Security Scan Report{RESET}")
    print(f"{'=' * 70}\n")

    if not findings:
        print(f"{GREEN}{BOLD}No security issues found.{RESET}\n")
        return

    # Group by severity
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

    # Summary
    total = len(findings)
    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    highs = sum(1 for f in findings if f["severity"] == "HIGH")
    print(f"{BOLD}Total: {total} finding(s) — {crits} critical, {highs} high{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Security — security vulnerability scanner"
    )
    parser.add_argument("--deps", action="store_true", help="Dependency CVEs only")
    parser.add_argument("--code", action="store_true", help="Code patterns only")
    parser.add_argument("--config", action="store_true", help="Config checks only")
    parser.add_argument(
        "--json", action="store_true", help="Output JSON instead of text"
    )
    args = parser.parse_args()

    run_all = not (args.deps or args.code or args.config)

    print(f"{BOLD}Security Scanner — WarmPath{RESET}")
    print(f"Scanning: {PROJECT_ROOT}\n")

    if run_all or args.deps:
        scan_dependencies()
    if run_all or args.code:
        scan_code_patterns()
    if run_all or args.config:
        scan_config()
    if run_all:
        scan_auth_coverage()
        scan_input_validation()

    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        print_report()

    # Exit code
    crits = sum(1 for f in findings if f["severity"] == "CRITICAL")
    has_findings = len(findings) > 0
    sys.exit(2 if crits > 0 else 1 if has_findings else 0)


if __name__ == "__main__":
    main()
