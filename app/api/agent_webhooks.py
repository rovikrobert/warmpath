"""Webhook endpoints for agent runtime event ingestion.

GitHub push/PR events are verified via HMAC signature, converted to
agent runtime events, and dispatched to the LangGraph runtime.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from app.agent_runtime.events.ingestion import create_event
from app.config import settings
from app.utils.redis_streams import stream_add

router = APIRouter()

_GITHUB_WEBHOOK_SECRET = settings.GITHUB_AGENT_WEBHOOK_SECRET
_runtime_enabled = settings.AGENT_RUNTIME_ENABLED


def _verify_github_signature(body: bytes, signature: str | None) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not _GITHUB_WEBHOOK_SECRET or not signature:
        return False
    expected = (
        "sha256="
        + hmac.new(_GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


@router.post("/github", status_code=202)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict[str, Any]:
    """Receive GitHub webhooks and convert to agent runtime events."""
    if not _runtime_enabled:
        raise HTTPException(status_code=503, detail="Agent runtime disabled")

    body = await request.body()

    if not _verify_github_signature(body, x_hub_signature_256):
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

    await stream_add("warmpath:agent_events", {"event": json.dumps(event)})
    return {"status": "accepted", "dedup_key": event["dedup_key"]}
