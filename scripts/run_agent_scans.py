"""Run all agent team scans, then generate CoS daily brief.

Designed for Railway Cron: runs to completion and exits.
Set SERVICE_ROLE=scan in the Railway cron service env vars.

Budget: each full scan costs ~$0.10-0.50 depending on model.
The $3/day budget allows multiple runs comfortably.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scan] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Teams to scan, in dependency order (engineering first — others may reference it)
TEAM_SCANS = [
    ("engineering", ["python3", "-m", "agents.orchestrator", "--all", "--skip-tests"]),
    ("data", ["python3", "-m", "data_team.orchestrator", "--all"]),
    ("product", ["python3", "-m", "product_team.orchestrator", "--all"]),
    ("ops", ["python3", "-m", "ops_team.orchestrator", "--all"]),
    ("finance", ["python3", "-m", "finance_team.orchestrator", "--all"]),
    ("gtm", ["python3", "-m", "gtm_team.orchestrator", "--all"]),
]

COS_DAILY = ["python3", "-m", "agents.orchestrator", "--cos-daily"]


def run_scan(name: str, cmd: list[str], timeout: int = 300) -> bool:
    """Run a single team scan. Returns True on success."""
    logger.info("Starting %s scan...", name)
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        elapsed = time.monotonic() - start
        if result.returncode == 0:
            logger.info("%s scan completed in %.1fs", name, elapsed)
            return True
        else:
            logger.error(
                "%s scan failed (exit %d, %.1fs): %s",
                name,
                result.returncode,
                elapsed,
                result.stderr[-500:] if result.stderr else "no stderr",
            )
            return False
    except subprocess.TimeoutExpired:
        logger.error("%s scan timed out after %ds", name, timeout)
        return False
    except Exception as e:
        logger.error("%s scan error: %s", name, e)
        return False


def main() -> None:
    logger.info("=== Agent scan cycle starting ===")
    start = time.monotonic()

    successes = 0
    failures = 0

    for name, cmd in TEAM_SCANS:
        if run_scan(name, cmd):
            successes += 1
        else:
            failures += 1
            # Continue scanning other teams even if one fails

    # Always run CoS daily brief (it works with whatever reports are available)
    logger.info("Generating CoS daily brief...")
    cos_ok = run_scan("cos-daily", COS_DAILY, timeout=120)

    elapsed = time.monotonic() - start
    logger.info(
        "=== Scan cycle complete: %d/%d teams OK, CoS %s, %.1fs total ===",
        successes,
        len(TEAM_SCANS),
        "OK" if cos_ok else "FAILED",
        elapsed,
    )

    # Exit 0 even if some teams failed — Railway Cron treats non-zero as failure
    # and may retry. Individual failures are logged and visible in Railway logs.
    sys.exit(0)


if __name__ == "__main__":
    main()
