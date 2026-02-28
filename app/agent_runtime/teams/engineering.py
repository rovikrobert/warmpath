"""Engineering team subgraph -- wraps existing agents/ scanners."""

from __future__ import annotations

import importlib
import logging
from typing import Any

from agents.shared.report import AgentReport

logger = logging.getLogger(__name__)

_SCANNER_MODULES = {
    "architect": "agents.architect.architect",
    "test_engineer": "agents.test_engineer.test_engineer",
    "perf_monitor": "agents.perf_monitor.perf_monitor",
    "deps_manager": "agents.deps_manager.deps_manager",
    "security": "agents.security_scan.security_scan",
    "privy": "agents.privy.privy",
}


def _run_scanner(module_path: str) -> AgentReport:
    mod = importlib.import_module(module_path)
    return mod.scan()


def run_existing_scanners(
    scanner_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    names = scanner_names or list(_SCANNER_MODULES.keys())
    all_findings: list[dict[str, Any]] = []

    for name in names:
        module_path = _SCANNER_MODULES.get(name)
        if not module_path:
            logger.warning("Unknown scanner: %s", name)
            continue

        try:
            report = _run_scanner(module_path)
            for finding in report.findings:
                d = (
                    finding.__dict__.copy()
                    if hasattr(finding, "__dict__")
                    else dict(finding)
                )
                d["source_team"] = "engineering"
                all_findings.append(d)
        except Exception as exc:
            logger.exception("Scanner %s failed: %s", name, exc)
            all_findings.append(
                {
                    "id": f"scanner_error_{name}",
                    "severity": "high",
                    "category": "infrastructure",
                    "title": f"Scanner {name} failed: {exc}",
                    "detail": str(exc),
                    "source_team": "engineering",
                    "recommendation": f"Investigate why {name} scanner is failing",
                    "effort_hours": 0.5,
                }
            )

    return all_findings
