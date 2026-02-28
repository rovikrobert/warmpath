from __futu[RESEND_KEY_REDACTED] import annotations


def format_escalation_message(
    event_type: str, priority: str, findings_count: int, summary: str
) -> str:
    priority_icon = {
        "critical": "[!!!]",
        "high": "[!!]",
        "medium": "[!]",
        "low": "[.]",
    }.get(priority, "[?]")
    lines = [
        f"{priority_icon} Agent Runtime — {priority.upper()} {event_type}",
        "",
        summary,
        "",
        f"Findings: {findings_count}",
        "",
        "Reply 'approve' to let agents act, or 'reject' to stop.",
    ]
    return "\n".join(lines)


async def send_escalation(
    event_type: str, priority: str, findings_count: int, summary: str
) -> None:
    import os

    import httpx

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    msg = format_escalation_message(event_type, priority, findings_count, summary)
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": msg},
        )
