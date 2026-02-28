"""Conditional Weave initialization for AI trace observability.

Weave is W&B's LLM tracing SDK. We only initialize it when:
1. AI_MOCK_MODE is disabled (real AI calls happening)
2. WANDB_API_KEY is set (credentials available)

Failure to initialize never crashes the app — returns False silently.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
import os

logger = logging.getLogger(__name__)


def init_weave() -> bool:
    """Initialize W&B Weave tracing if conditions are met.

    Returns True if Weave was successfully initialized, False otherwise.
    Catches all exceptions — Weave failure must never crash the app.
    """
    # Skip in mock mode (default) — no real AI calls to trace
    mock_mode = os.environ.get("AI_MOCK_MODE", "true").lower() == "true"
    if mock_mode:
        logger.debug("Weave init skipped: AI_MOCK_MODE is true")
        return False

    # Skip without API key — can't authenticate with W&B
    api_key = os.environ.get("WANDB_API_KEY", "")
    if not api_key.strip():
        logger.debug("Weave init skipped: WANDB_API_KEY not set")
        return False

    project_name = os.environ.get("WANDB_PROJECT", "warmpath-ai-traces")

    try:
        import weave  # Lazy import — heavy package

        weave.init(project_name=project_name)
        logger.info("Weave initialized: project=%s", project_name)
        return True
    except Exception:
        logger.warning("Weave initialization failed", exc_info=True)
        return False
