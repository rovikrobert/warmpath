"""Claude Agent SDK session runner.

Spawns a Claude Code SDK session to analyze scanner findings,
collects messages, and returns structured output with cost tracking.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def run_sdk_session(
    prompt: str,
    system_prompt: str,
    max_turns: int = 10,
    model: str = "claude-sonnet-4-20250514",
    allowed_tools: list[str] | None = None,
    cwd: str | None = None,
) -> dict[str, Any]:
    """Run a Claude Agent SDK session and return collected messages.

    Returns dict with:
        messages: list of {role, content} dicts
        model: model used
        cost_usd: actual cost from ResultMessage (or 0.0)
        num_turns: number of turns from ResultMessage (or 0)
    """
    # Lazy import — claude_code_sdk is only needed at runtime, not at
    # module load time.  This lets tests and CI run without it installed.
    from claude_code_sdk import ClaudeCodeOptions, query
    from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock

    options = ClaudeCodeOptions(
        system_prompt=system_prompt,
        max_turns=max_turns,
        model=model,
        allowed_tools=allowed_tools or ["Read", "Glob", "Grep"],
        permission_mode="default",
        cwd=cwd or "/app",
    )

    messages: list[dict[str, str]] = []
    cost_usd = 0.0
    num_turns = 0

    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            text_parts = [
                block.text for block in msg.content if isinstance(block, TextBlock)
            ]
            if text_parts:
                messages.append({"role": "assistant", "content": "\n".join(text_parts)})
        elif isinstance(msg, ResultMessage):
            cost_usd = msg.total_cost_usd or 0.0
            num_turns = msg.num_turns

    return {
        "messages": messages,
        "model": model,
        "cost_usd": cost_usd,
        "num_turns": num_turns,
    }
