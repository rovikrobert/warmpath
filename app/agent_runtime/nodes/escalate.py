"""Escalate node — determines whether human review is required."""

from __futu[RESEND_KEY_REDACTED] import annotations


def should_escalate(priority: str, max_trust_level: int) -> bool:
    """Decide if an event requires human escalation.

    The decision is based on the combination of event priority and the
    highest trust level among the agents that have processed it:

    * **critical** priority always escalates unless handled by a trusted
      contributor (trust level >= 2).
    * **high** priority escalates when no agent has at least *member*
      trust (level >= 1).
    * **medium** / **low** never auto-escalate.
    """
    if priority == "critical" and max_trust_level < 2:
        return True
    return bool(priority == "high" and max_trust_level < 1)
