"""Base class for team runners with SDK augmentation support."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from agents.shared.report import AgentReport

from app.agent_runtime.cost_guard import BudgetStatus, select_model
from app.agent_runtime.trust import TrustLevel, get_allowed_tools, get_max_turns

logger = logging.getLogger(__name__)

# Map team_name → report directory so scanners can save *_latest.json
# for the CoS _load_reports() pipeline.
_TEAM_REPORTS_DIRS: dict[str, Path | None] = {}


def _resolve_reports_dir(team_name: str) -> Path | None:
    """Lazily resolve the report directory for a team."""
    if team_name in _TEAM_REPORTS_DIRS:
        return _TEAM_REPORTS_DIRS[team_name]

    if team_name == "engineering":
        from agents.shared.config import REPORTS_DIR

        _TEAM_REPORTS_DIRS[team_name] = REPORTS_DIR
        return REPORTS_DIR

    config_module = f"{team_name}_team.shared.config"
    try:
        mod = importlib.import_module(config_module)
        _TEAM_REPORTS_DIRS[team_name] = mod.REPORTS_DIR
        return mod.REPORTS_DIR
    except ImportError:
        logger.warning("Cannot resolve reports dir for %s team", team_name)
        _TEAM_REPORTS_DIRS[team_name] = None
        return None


class TeamRunner:
    """Base class for team scanner wrappers with optional SDK augmentation.

    Subclasses define ``team_name`` and ``scanner_modules``.
    The ``run()`` method executes: scan → SDK augment → return findings.
    """

    team_name: str = ""
    scanner_modules: dict[str, str] = {}

    def _run_scanner(self, module_path: str) -> AgentReport:
        mod = importlib.import_module(module_path)
        return mod.scan()

    def _save_report(self, report: AgentReport) -> None:
        """Persist AgentReport as {agent}_latest.json for CoS daily brief.

        Refuses to overwrite a real report with a stub (scan_duration == 0
        and <= 1 finding with no metrics). This prevents failed scanners
        from clobbering legitimate data.
        """
        reports_dir = _resolve_reports_dir(self.team_name)
        if reports_dir is None:
            return
        try:
            import json as _json

            reports_dir.mkdir(parents=True, exist_ok=True)
            path = reports_dir / f"{report.agent}_latest.json"

            # Guard: don't overwrite a real report with a stub
            if (
                report.scan_duration_seconds == 0
                and len(report.findings) <= 1
                and not report.metrics
                and path.exists()
            ):
                try:
                    existing = _json.loads(path.read_text(encoding="utf-8"))
                    if (
                        existing.get("scan_duration_seconds", 0) > 0
                        or len(existing.get("findings", [])) > 1
                    ):
                        logger.warning(
                            "Refusing to overwrite real %s report with stub "
                            "(scan_duration=0, %d findings)",
                            report.agent,
                            len(report.findings),
                        )
                        return
                except (ValueError, OSError):
                    pass  # Existing file is corrupt — ok to overwrite

            path.write_text(report.serialize(), encoding="utf-8")
        except Exception:
            logger.debug(
                "Failed to save report %s for %s",
                report.agent,
                self.team_name,
                exc_info=True,
            )

    def run_scanners(
        self, scanner_names: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Run all scanners, collect findings."""
        names = scanner_names or list(self.scanner_modules.keys())
        all_findings: list[dict[str, Any]] = []

        for name in names:
            module_path = self.scanner_modules.get(name)
            if not module_path:
                logger.warning("Unknown scanner: %s", name)
                continue

            try:
                report = self._run_scanner(module_path)
                self._save_report(report)
                for finding in report.findings:
                    d = (
                        finding.__dict__.copy()
                        if hasattr(finding, "__dict__")
                        else dict(finding)
                    )
                    d["source_team"] = self.team_name
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
                        "source_team": self.team_name,
                        "recommendation": (
                            f"Investigate why {name} scanner is failing"
                        ),
                        "effort_hours": 0.5,
                    }
                )

        return all_findings

    async def augment_with_sdk(
        self,
        findings: list[dict[str, Any]],
        event: dict[str, Any],
        trust_level: int,
        budget_status: str,
    ) -> list[dict[str, Any]]:
        """Spawn SDK session to analyze findings.

        Only runs if trust >= RECOMMENDER and budget is not exceeded.
        """
        if trust_level < TrustLevel.RECOMMENDER:
            return findings

        model = select_model("claude-sonnet-4-20250514", BudgetStatus(budget_status))
        if model is None:
            logger.info("SDK augmentation skipped: budget exceeded")
            return findings

        # Lazy imports — keeps module importable without claude_code_sdk
        from app.agent_runtime.sdk.parser import merge_findings, parse_sdk_output
        from app.agent_runtime.sdk.prompts import (
            build_augmentation_prompt,
            get_system_prompt,
        )
        from app.agent_runtime.sdk.runner import run_sdk_session

        prompt = build_augmentation_prompt(self.team_name, findings, event)
        allowed_tools = get_allowed_tools(TrustLevel(trust_level))
        max_turns = get_max_turns(TrustLevel(trust_level))

        try:
            result = await run_sdk_session(
                prompt=prompt,
                system_prompt=get_system_prompt(),
                max_turns=max_turns,
                model=model,
                allowed_tools=allowed_tools,
            )

            # Record actual SDK cost for daily budget tracking
            cost_usd = result.get("cost_usd", 0.0)
            if cost_usd > 0:
                try:
                    from app.agent_runtime.redis_store import AgentRuntimeRedis
                    from app.config import settings

                    store = AgentRuntimeRedis(redis_url=settings.REDIS_URL)
                    await store.record_spend(cost_usd)
                except Exception:
                    logger.debug("Failed to record SDK spend", exc_info=True)

            augmented = parse_sdk_output(result["messages"], self.team_name)
            return merge_findings(findings, augmented)
        except Exception:
            logger.exception("SDK augmentation failed for %s", self.team_name)
            return findings

    async def run(
        self,
        event: dict[str, Any],
        trust_level: int = TrustLevel.RECOMMENDER,
        budget_status: str = BudgetStatus.OK,
    ) -> list[dict[str, Any]]:
        """Full pipeline: scan → augment → return."""
        findings = self.run_scanners()
        if findings:
            findings = await self.augment_with_sdk(
                findings, event, trust_level, budget_status
            )
        return findings
