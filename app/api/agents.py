"""Agent run endpoint — trigger agent scans from Railway cron or external triggers."""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import subprocess
import sys
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
    "engineering-skip-tests": [
        "python3",
        "-m",
        "agents.orchestrator",
        "--all",
        "--skip-tests",
    ],
    "engineering-weekly": ["python3", "-m", "agents.orchestrator", "--weekly"],
    "data": ["python3", "-m", "data_team.orchestrator", "--all"],
    "data-weekly": ["python3", "-m", "data_team.orchestrator", "--weekly"],
    "data-monthly": ["python3", "-m", "data_team.orchestrator", "--monthly"],
    "product": ["python3", "-m", "product_team.orchestrator", "--all"],
    "product-weekly": ["python3", "-m", "product_team.orchestrator", "--weekly"],
    "product-monthly": ["python3", "-m", "product_team.orchestrator", "--monthly"],
    "ops": ["python3", "-m", "ops_team.orchestrator", "--all"],
    "ops-weekly": ["python3", "-m", "ops_team.orchestrator", "--weekly"],
    "ops-monthly": ["python3", "-m", "ops_team.orchestrator", "--monthly"],
    "finance": ["python3", "-m", "finance_team.orchestrator", "--all"],
    "finance-weekly": ["python3", "-m", "finance_team.orchestrator", "--weekly"],
    "finance-monthly": ["python3", "-m", "finance_team.orchestrator", "--monthly"],
    "gtm": ["python3", "-m", "gtm_team.orchestrator", "--all"],
    "gtm-weekly": ["python3", "-m", "gtm_team.orchestrator", "--weekly"],
    "gtm-monthly": ["python3", "-m", "gtm_team.orchestrator", "--monthly"],
}

# Full scan runs all teams then CoS — one trigger does everything
_FULL_SCAN_ORDER = [
    "engineering-skip-tests",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
    "cos-daily",
]

# Weekly: team scans → team weekly briefs → CoS weekly
_WEEKLY_SCAN_ORDER = [
    "engineering-skip-tests",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
    "engineering-weekly",
    "data-weekly",
    "product-weekly",
    "ops-weekly",
    "finance-weekly",
    "gtm-weekly",
    "cos-weekly",
]

# Monthly: team scans → team monthly briefs → CoS weekly (as synthesis)
_MONTHLY_SCAN_ORDER = [
    "engineering-skip-tests",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
    "data-monthly",
    "product-monthly",
    "ops-monthly",
    "finance-monthly",
    "gtm-monthly",
    "cos-weekly",
]

RunMode = Literal[
    "cos-daily",
    "cos-weekly",
    "engineering",
    "engineering-skip-tests",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
    "full-scan",
    "full-scan-weekly",
    "full-scan-monthly",
]

# Track active/recent runs for status endpoint
_run_log: list[dict] = []


def _log(msg: str) -> None:
    """Print to stdout with flush — guaranteed to appear in Railway logs."""
    print(msg, flush=True)


def _run_agent(mode: str) -> dict:
    """Execute an agent command in a subprocess. Pipes output to stdout."""
    cmd = _COMMANDS[mode]
    label = f"[agent:{mode}]"
    _log(f"{label} started → {' '.join(cmd)}")

    entry = {
        "mode": mode,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
    }
    _run_log.append(entry)
    if len(_run_log) > 50:
        _run_log.pop(0)

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
            timeout=600,
        )
        elapsed = time.monotonic() - start

        if result.returncode == 0:
            _log(f"{label} completed in {elapsed:.1f}s")
            entry["status"] = "completed"
        else:
            _log(f"{label} FAILED (exit {result.returncode}, {elapsed:.1f}s)")
            entry["status"] = "failed"

        entry["elapsed_s"] = round(elapsed, 1)
        return entry

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        _log(f"{label} TIMED OUT after {elapsed:.1f}s")
        entry["status"] = "timeout"
        entry["elapsed_s"] = round(elapsed, 1)
        return entry
    except Exception as exc:
        _log(f"{label} ERROR: {exc}")
        entry["status"] = "error"
        entry["error"] = str(exc)[:500]
        return entry


def _run_full_scan() -> None:
    """Run all teams in sequence, then CoS daily. Single trigger for everything."""
    # Separate team scans from cos-daily — cos-daily only makes sense if teams produced data
    team_modes = [m for m in _FULL_SCAN_ORDER if not m.startswith("cos-")]
    cos_modes = [m for m in _FULL_SCAN_ORDER if m.startswith("cos-")]

    _log(
        f"[full-scan] Starting ({len(_FULL_SCAN_ORDER)} steps: {' → '.join(_FULL_SCAN_ORDER)})"
    )
    start = time.monotonic()
    results = []
    failed_teams = []

    for i, mode in enumerate(team_modes, 1):
        _log(f"[full-scan] Step {i}/{len(_FULL_SCAN_ORDER)}: {mode}")
        result = _run_agent(mode)
        results.append(result)
        if result["status"] != "completed":
            failed_teams.append(mode)
            _log(f"[full-scan] WARNING: {mode} → {result['status']}")

    team_succeeded = len(team_modes) - len(failed_teams)

    if team_succeeded == 0:
        _log(
            f"[full-scan] ABORTING cos-daily — all {len(team_modes)} team scans failed: "
            f"{failed_teams}. CoS brief would be empty/misleading."
        )
    else:
        if failed_teams:
            _log(
                f"[full-scan] WARNING: {len(failed_teams)} team scan(s) failed: "
                f"{failed_teams}. CoS brief will be incomplete."
            )
        for i, mode in enumerate(cos_modes, len(team_modes) + 1):
            _log(f"[full-scan] Step {i}/{len(_FULL_SCAN_ORDER)}: {mode}")
            result = _run_agent(mode)
            results.append(result)
            if result["status"] != "completed":
                _log(f"[full-scan] {mode} → {result['status']}")

    elapsed = time.monotonic() - start
    completed = sum(1 for r in results if r["status"] == "completed")
    _log(f"[full-scan] Done in {elapsed:.1f}s — {completed}/{len(results)} succeeded")


def _run_full_scan_weekly() -> None:
    """Run all teams, their weekly briefs, then CoS weekly."""
    tag = "full-scan-weekly"
    team_modes = [m for m in _WEEKLY_SCAN_ORDER if not m.startswith("cos-")]
    cos_modes = [m for m in _WEEKLY_SCAN_ORDER if m.startswith("cos-")]

    _log(f"[{tag}] Starting ({len(_WEEKLY_SCAN_ORDER)} steps: {' → '.join(_WEEKLY_SCAN_ORDER)})")
    start = time.monotonic()
    results = []
    failed = []

    for i, mode in enumerate(team_modes, 1):
        _log(f"[{tag}] Step {i}/{len(_WEEKLY_SCAN_ORDER)}: {mode}")
        result = _run_agent(mode)
        results.append(result)
        if result["status"] != "completed":
            failed.append(mode)
            _log(f"[{tag}] WARNING: {mode} → {result['status']}")

    # Only run CoS if at least one base scan succeeded
    base_scans = [m for m in team_modes if "-weekly" not in m]
    base_failed = [m for m in failed if m in base_scans]
    if len(base_failed) == len(base_scans):
        _log(f"[{tag}] ABORTING cos-weekly — all base scans failed: {base_failed}")
    else:
        if failed:
            _log(f"[{tag}] WARNING: {len(failed)} step(s) failed: {failed}")
        for i, mode in enumerate(cos_modes, len(team_modes) + 1):
            _log(f"[{tag}] Step {i}/{len(_WEEKLY_SCAN_ORDER)}: {mode}")
            result = _run_agent(mode)
            results.append(result)
            if result["status"] != "completed":
                _log(f"[{tag}] {mode} → {result['status']}")

    elapsed = time.monotonic() - start
    completed = sum(1 for r in results if r["status"] == "completed")
    _log(f"[{tag}] Done in {elapsed:.1f}s — {completed}/{len(results)} succeeded")


def _run_full_scan_monthly() -> None:
    """Run all teams, their monthly briefs, then CoS weekly synthesis."""
    tag = "full-scan-monthly"
    team_modes = [m for m in _MONTHLY_SCAN_ORDER if not m.startswith("cos-")]
    cos_modes = [m for m in _MONTHLY_SCAN_ORDER if m.startswith("cos-")]

    _log(f"[{tag}] Starting ({len(_MONTHLY_SCAN_ORDER)} steps: {' → '.join(_MONTHLY_SCAN_ORDER)})")
    start = time.monotonic()
    results = []
    failed = []

    for i, mode in enumerate(team_modes, 1):
        _log(f"[{tag}] Step {i}/{len(_MONTHLY_SCAN_ORDER)}: {mode}")
        result = _run_agent(mode)
        results.append(result)
        if result["status"] != "completed":
            failed.append(mode)
            _log(f"[{tag}] WARNING: {mode} → {result['status']}")

    # Only run CoS if at least one base scan succeeded
    base_scans = [m for m in team_modes if "-monthly" not in m]
    base_failed = [m for m in failed if m in base_scans]
    if len(base_failed) == len(base_scans):
        _log(f"[{tag}] ABORTING cos-weekly — all base scans failed: {base_failed}")
    else:
        if failed:
            _log(f"[{tag}] WARNING: {len(failed)} step(s) failed: {failed}")
        for i, mode in enumerate(cos_modes, len(team_modes) + 1):
            _log(f"[{tag}] Step {i}/{len(_MONTHLY_SCAN_ORDER)}: {mode}")
            result = _run_agent(mode)
            results.append(result)
            if result["status"] != "completed":
                _log(f"[{tag}] {mode} → {result['status']}")

    elapsed = time.monotonic() - start
    completed = sum(1 for r in results if r["status"] == "completed")
    _log(f"[{tag}] Done in {elapsed:.1f}s — {completed}/{len(results)} succeeded")


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
        - full-scan-weekly: all teams + weekly briefs + CoS weekly
        - full-scan-monthly: all teams + monthly briefs + CoS weekly synthesis

    Protected by AGENT_RUN_SECRET header. Returns immediately.
    """
    _verify_secret(x_agent_secret)

    if mode == "full-scan":
        background_tasks.add_task(_run_full_scan)
    elif mode == "full-scan-weekly":
        background_tasks.add_task(_run_full_scan_weekly)
    elif mode == "full-scan-monthly":
        background_tasks.add_task(_run_full_scan_monthly)
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
            json_files = sorted(
                report_dir.glob("*_latest.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if json_files:
                mtime = datetime.fromtimestamp(
                    json_files[0].stat().st_mtime, tz=timezone.utc
                )
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
