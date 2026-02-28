"""Gemini Batch API integration for large CSV cleanup.

Submits all cleanup batches as a single async batch job at 50% token cost.
Used when contact count exceeds GEMINI_BATCH_THRESHOLD (default 5,000).
"""

from __futu[RESEND_KEY_REDACTED] import annotations

import contextlib
import json
import logging

from app.services.ai_csv_cleaner import (
    _build_cleanup_payload,
    build_cached_cleanup_content,
)

logger = logging.getLogger(__name__)

GEMINI_BATCH_MODEL = "gemini-2.0-flash"


async def submit_cleanup_batch(
    client: object,
    batches: list[list[dict]],
    upload_id: str,
) -> str | None:
    """Submit all cleanup batches as a single Gemini batch job.

    Args:
        client: Gemini client instance.
        batches: List of contact batches (each batch is a list of contact dicts).
        upload_id: CSV upload ID for display name.

    Returns:
        Batch job name (e.g. "batches/abc123") or None on failure.
    """
    try:
        cached_content = build_cached_cleanup_content()

        inline_requests = []
        for i, batch in enumerate(batches):
            payload = _build_cleanup_payload(batch)
            inline_requests.append(
                {
                    "key": f"chunk-{i}",
                    "contents": [
                        {
                            "parts": [{"text": json.dumps(payload)}],
                            "role": "user",
                        }
                    ],
                    "config": {
                        "system_instruction": {"parts": [{"text": cached_content}]},
                        "response_mime_type": "application/json",
                        "temperature": 0,
                        "max_output_tokens": 8192,
                    },
                }
            )

        batch_job = client.batches.create(
            model=GEMINI_BATCH_MODEL,
            src=inline_requests,
            config={"display_name": f"csv-clean-{upload_id}"},
        )

        logger.info(
            "Submitted Gemini batch job %s for upload %s (%d chunks)",
            batch_job.name,
            upload_id,
            len(batches),
        )
        return batch_job.name

    except Exception:
        logger.warning(
            "Failed to submit Gemini batch for upload %s",
            upload_id,
            exc_info=True,
        )
        return None


TERMINAL_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


async def get_batch_results(
    client: object, job_name: str
) -> tuple[str, list[list[dict]] | None]:
    """Check batch job status and retrieve results if complete.

    Returns:
        Tuple of (state_name, results_or_none).
        results is a list of cleaned contact lists (one per chunk), or None if not done.
        Returns ("POLL_ERROR", None) on transient API errors so callers can retry.
    """
    try:
        job = client.batches.get(name=job_name)
    except Exception:
        logger.warning(
            "Failed to poll batch job %s, will retry", job_name, exc_info=True
        )
        return "POLL_ERROR", None
    state = job.state.name

    if state != "JOB_STATE_SUCCEEDED":
        return state, None

    # Parse responses into (chunk_index, contacts) pairs
    indexed_results: list[tuple[int, list[dict]]] = []
    for resp in job.dest.inlined_responses:
        # Extract chunk index from key (e.g. "chunk-3" → 3)
        chunk_idx = 0
        if hasattr(resp, "key") and resp.key:
            with contextlib.suppress(ValueError, IndexError):
                chunk_idx = int(resp.key.split("-", 1)[1])

        if resp.error:
            logger.warning("Batch chunk %d error: %s", chunk_idx, resp.error)
            indexed_results.append((chunk_idx, []))
            continue
        try:
            parsed = json.loads(resp.response.text)
            if isinstance(parsed, list):
                indexed_results.append((chunk_idx, parsed))
            elif isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list):
                        indexed_results.append((chunk_idx, v))
                        break
                else:
                    indexed_results.append((chunk_idx, [parsed]))
            else:
                indexed_results.append((chunk_idx, []))
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse batch chunk %d response", chunk_idx)
            indexed_results.append((chunk_idx, []))

    # Sort by chunk index to guarantee correct ordering
    indexed_results.sort(key=lambda x: x[0])
    results = [contacts for _, contacts in indexed_results]

    return state, results
