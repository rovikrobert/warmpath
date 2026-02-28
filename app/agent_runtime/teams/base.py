"""Base class for team runners with SDK augmentation support."""

from __futu[RESEND_KEY_REDACTED] import annotations

import importlib
import logging
from typing import Any

from agents.shared.report import AgentReport

from app.agent_runtime.cost_guard import BudgetStatus, select_model
from app.agent_runtime.trust import TrustLevel, get_allowed_tools, get_max_turns

logger = logging.getLogger(__name__)


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
