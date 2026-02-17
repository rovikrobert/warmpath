"""Agent run endpoint — trigger agent scans from Railway cron or external triggers."""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Valid run modes and their corresponding CLI commands
_COMMANDS: dict[str, list[str]] = {
    "cos-daily": ["python3", "-m", "agents.orchestrator", "--cos-daily"],
    "cos-weekly": ["python3", "-m", "agents.orchestrator", "--cos-weekly"],
    "engineering": ["python3", "-m", "agents.orchestrator", "--all"],
    "data": ["python3", "-m", "data_team.orchestrator", "--all"],
    "product": ["python3", "-m", "product_team.orchestrator", "--all"],
    "ops": ["python3", "-m", "ops_team.orchestrator", "--all"],
    "finance": ["python3", "-m", "finance_team.orchestrator", "--all"],
    "gtm": ["python3", "-m", "gtm_team.orchestrator", "--all"],
}

# Full scan runs all teams then CoS — one trigger does everything
_FULL_SCAN_ORDER = ["engineering", "data", "product", "ops", "finance", "gtm", "cos-daily"]

RunMode = Literal[
    "cos-daily",
    "cos-weekly",
    "engineering",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
    "full-scan",
]

# Track active/recent runs for status endpoint
_run_log: list[dict] = []


def _run_agent(mode: str) -> dict:
    """Execute an agent command in a subprocess. Streams stdout/stderr to logger."""
    cmd = _COMMANDS[mode]
    label = f"[{mode}]"
    logger.info("%s started → %s", label, " ".join(cmd))

    entry = {"mode": mode, "started_at": datetime.now(timezone.utc).isoformat(), "status": "running"}
    _run_log.append(entry)
    # Keep log bounded
    if len(_run_log) > 50:
        _run_log.pop(0)

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            captu[RESEND_KEY_REDACTED]=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        elapsed = time.monotonic() - start

        if result.returncode == 0:
            logger.info("%s completed in %.1fs", label, elapsed)
            # Log last 5 lines of stdout for visibility
            stdout_tail = "\n".join(result.stdout.strip().splitlines()[-5:])
            if stdout_tail:
                logger.info("%s output:\n%s", label, stdout_tail)
            entry["status"] = "completed"
        else:
            logger.error(
                "%s failed (exit %d, %.1fs)\nstderr: %s",
                label,
                result.returncode,
                elapsed,
                result.stderr[:2000],
            )
            entry["status"] = "failed"
            entry["error"] = result.stderr[:500]

        entry["elapsed_s"] = round(elapsed, 1)
        return entry

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        logger.error("%s timed out after %.1fs", label, elapsed)
        entry["status"] = "timeout"
        entry["elapsed_s"] = round(elapsed, 1)
        return entry
    except Exception as exc:
        logger.exception("%s error: %s", label, exc)
        entry["status"] = "error"
        entry["error"] = str(exc)[:500]
        return entry


def _run_full_scan() -> None:
    """Run all teams in sequence, then CoS daily. Single trigger for everything."""
    logger.info("[full-scan] Starting full agent scan (%d steps)", len(_FULL_SCAN_ORDER))
    start = time.monotonic()
    results = []

    for mode in _FULL_SCAN_ORDER:
        result = _run_agent(mode)
        results.append(result)
        # If a team scan fails, still continue with the rest
        if result["status"] != "completed":
            logger.warning("[full-scan] %s finished with status: %s — continuing", mode, result["status"])

    elapsed = time.monotonic() - start
    completed = sum(1 for r in results if r["status"] == "completed")
    logger.info(
        "[full-scan] Done in %.1fs — %d/%d succeeded",
        elapsed,
        completed,
        len(results),
    )


def _verify_secret(x_agent_secret: str) -> None:
    """Verify the agent run secret."""
    if not settings.AGENT_RUN_SECRET:
        raise HTTPException(status_code=503, detail="Agent runs not configured")
    if x_agent_secret != settings.AGENT_RUN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid agent secret")


@router.post("/run")
async def run_agents(
    background_tasks: BackgroundTasks,
    mode: RunMode = "cos-daily",
    x_agent_secret: str = Header(...),
) -> dict:
    """Trigger an agent run in the background.

    Modes:
        - engineering/data/product/ops/finance/gtm: run one team scan
        - cos-daily/cos-weekly: synthesize existing reports into founder brief
        - full-scan: run ALL teams then CoS daily (one trigger does everything)

    Protected by AGENT_RUN_SECRET header. Returns immediately.
    """
    _verify_secret(x_agent_secret)

    if mode == "full-scan":
        background_tasks.add_task(_run_full_scan)
    else:
        background_tasks.add_task(_run_agent, mode)

    return {
        "data": {"status": "started", "mode": mode},
        "meta": {"message": f"Agent run '{mode}' started in background"},
    }


@router.get("/status")
async def agent_status(
    x_agent_secret: str = Header(...),
) -> dict:
    """Return recent agent run history and report freshness."""
    _verify_secret(x_agent_secret)

    # Check report file timestamps
    report_dirs = {
        "engineering": Path("agents/reports"),
        "data": Path("data_team/reports"),
        "product": Path("product_team/reports"),
        "ops": Path("ops_team/reports"),
        "finance": Path("finance_team/reports"),
        "gtm": Path("gtm_team/reports"),
    }

    report_freshness: dict[str, str | None] = {}
    for team, report_dir in report_dirs.items():
        if report_dir.is_dir():
            json_files = sorted(report_dir.glob("*_latest.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if json_files:
                mtime = datetime.fromtimestamp(json_files[0].stat().st_mtime, tz=timezone.utc)
                report_freshness[team] = mtime.isoformat()
            else:
                report_freshness[team] = None
        else:
            report_freshness[team] = None

    return {
        "data": {
            "recent_runs": _run_log[-20:],
            "report_freshness": report_freshness,
        },
        "meta": {},
    }
