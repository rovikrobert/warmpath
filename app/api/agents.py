"""Agent run endpoint — trigger agent scans from Railway cron or external triggers."""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import subprocess
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

RunMode = Literal[
    "cos-daily",
    "cos-weekly",
    "engineering",
    "data",
    "product",
    "ops",
    "finance",
    "gtm",
]


def _run_agent(mode: str) -> None:
    """Execute an agent command in a subprocess."""
    cmd = _COMMANDS[mode]
    logger.info("Agent run started: %s → %s", mode, " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            captu[RESEND_KEY_REDACTED]=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )
        if result.returncode == 0:
            logger.info("Agent run completed: %s", mode)
        else:
            logger.error(
                "Agent run failed: %s (exit %d)\nstderr: %s",
                mode,
                result.returncode,
                result.stderr[:2000],
            )
    except subprocess.TimeoutExpired:
        logger.error("Agent run timed out: %s", mode)
    except Exception:
        logger.exception("Agent run error: %s", mode)


@router.post("/run")
async def run_agents(
    background_tasks: BackgroundTasks,
    mode: RunMode = "cos-daily",
    x_agent_secret: str = Header(...),
) -> dict:
    """Trigger an agent run in the background.

    Protected by AGENT_RUN_SECRET header. Returns immediately while the
    agent scan runs asynchronously.
    """
    if not settings.AGENT_RUN_SECRET:
        raise HTTPException(status_code=503, detail="Agent runs not configured")

    if x_agent_secret != settings.AGENT_RUN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid agent secret")

    background_tasks.add_task(_run_agent, mode)

    return {
        "data": {"status": "started", "mode": mode},
        "meta": {"message": f"Agent run '{mode}' started in background"},
    }
