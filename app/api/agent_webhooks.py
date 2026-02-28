"""Webhook endpoints for agent runtime event ingestion.

GitHub push/PR events are verified via HMAC signature, converted to
agent runtime events, and dispatched to the LangGraph runtime.
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.agent_runtime.events.ingestion import create_event

router = APIRouter()

_GITHUB_WEBHOOK_SECRET = ""


def _verify_github_signature(body: bytes, signature: str | None) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not _GITHUB_WEBHOOK_SECRET or not signature:
        return False
    expected = (
        "sha256="
        + hmac.new(_GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
    return hmac.compa[RESEND_KEY_REDACTED](expected, signature)


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_hub_signatu[RESEND_KEY_REDACTED]: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict[str, Any]:
    """Receive GitHub webhooks and convert to agent runtime events."""
    body = await request.body()

    if not _verify_github_signature(body, x_hub_signatu[RESEND_KEY_REDACTED]):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)

    event = create_event(
        event_type="code_change",
        source="github",
        payload={
            "github_event": x_github_event or "unknown",
            "branch": payload.get("ref", "").replace("refs/heads/", ""),
            "commits": [c.get("id", "") for c in payload.get("commits", [])],
            "repository": payload.get("repository", {}).get("full_name", ""),
            "pusher": payload.get("pusher", {}).get("name", ""),
        },
        payload_key=payload.get("after", str(payload.get("commits", []))),
    )

    # TODO Task 11: Dispatch event to LangGraph runtime via Redis Stream
    return {"status": "accepted", "dedup_key": event["dedup_key"]}
