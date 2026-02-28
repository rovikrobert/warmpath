"""Graduated trust model for agent autonomy."""

from __futu[RESEND_KEY_REDACTED] import annotations

from enum import IntEnum


class TrustLevel(IntEnum):
    OBSERVER = 0
    RECOMMENDER = 1
    CONTRIBUTOR = 2
    DEPLOYER = 3


_TOOLS_BY_LEVEL: dict[int, list[str]] = {
    0: ["Read", "Glob", "Grep"],
    1: ["Read", "Glob", "Grep", "WebSearch", "WebFetch"],
    2: ["Read", "Glob", "Grep", "WebSearch", "WebFetch", "Edit", "Write", "Bash"],
    3: [
        "Read",
        "Glob",
        "Grep",
        "WebSearch",
        "WebFetch",
        "Edit",
        "Write",
        "Bash",
        "Task",
    ],
}

_MAX_TURNS: dict[int, int] = {0: 10, 1: 15, 2: 30, 3: 30}


def get_allowed_tools(level: TrustLevel) -> list[str]:
    """Return Claude Agent SDK tool names allowed at this trust level."""
    return list(_TOOLS_BY_LEVEL.get(int(level), _TOOLS_BY_LEVEL[0]))


def get_max_turns(level: TrustLevel) -> int:
    """Return max agent loop turns allowed at this trust level."""
    return _MAX_TURNS.get(int(level), _MAX_TURNS[0])
