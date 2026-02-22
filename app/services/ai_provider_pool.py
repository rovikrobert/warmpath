"""Multi-provider AI cleaning pool.

Dispatches CSV cleaning batches across all configured AI providers
(Gemini 2.0 Flash, Claude Haiku, GPT-4o-mini, Groq Llama 3.3)
for maximum throughput. Each provider has its own rate limiter. The
dispatcher tries providers in priority order with fast-fail retry and
falls back to mock cleaning.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.config import settings
from app.services.ai_csv_cleaner import (
    _build_cleanup_payload,
    _CLEANUP_SYSTEM_PROMPT,
    clean_contacts_mock,
    post_process_ai_output,
)
from app.utils.rate_limiter import acquire_slot, release_slot

logger = logging.getLogger(__name__)


def _extract_contacts_array(parsed: Any) -> list[dict]:
    """Extract the contacts array from various AI response formats.

    OpenAI JSON mode requires top-level objects, so providers may wrap
    the array like {"contacts": [...]} or {"result": [...]}.
    This normalises both raw arrays and wrapped objects.
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for v in parsed.values():
            if isinstance(v, list):
                return v
        # Single contact wrapped in object
        return [parsed]
    return []


# ---------------------------------------------------------------------------
# Provider definitions
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS = {
    "gemini": {
        "model": "gemini-2.0-flash",
        "key_attr": "GOOGLE_API_KEY",
        "max_concurrent_attr": "GOOGLE_MAX_CONCURRENT",
        "max_tokens": 65536,
    },
    "anthropic": {
        "model": "claude-haiku-4-5-20251001",
        "key_attr": "ANTHROPIC_API_KEY",
        "max_concurrent_attr": "ANTHROPIC_MAX_CONCURRENT",
        "max_tokens": 16384,
    },
    "openai": {
        "model": "gpt-4o-mini",
        "key_attr": "OPENAI_API_KEY",
        "max_concurrent_attr": "OPENAI_MAX_CONCURRENT",
        "max_tokens": 16384,
    },
    "groq": {
        "model": "openai/gpt-oss-20b",
        "key_attr": "GROQ_API_KEY",
        "max_concurrent_attr": "GROQ_MAX_CONCURRENT",
        "max_tokens": 65536,
    },
}


@dataclass
class CleaningProvider:
    name: str
    model: str
    max_concurrent: int
    get_client: Callable[[], Any]
    call: Callable  # async (client, system_prompt, payload) -> list[dict]


def _is_provider_enabled(name: str, cfg: Any = None) -> bool:
    """Check if a provider has its API key (or Vertex AI credentials) configured."""
    cfg = cfg or settings
    key_attr = PROVIDER_CONFIGS[name]["key_attr"]
    key = getattr(cfg, key_attr, "")
    if key and key.strip():
        return True
    # Vertex AI mode: service account JSON enables Google without an API key
    if name == "gemini":
        sa = getattr(cfg, "GOOGLE_SERVICE_ACCOUNT_JSON", "")
        return bool(sa and sa.strip())
    return False


# ---------------------------------------------------------------------------
# Provider-specific call implementations
# ---------------------------------------------------------------------------


async def _call_gemini(
    client: Any, system_prompt: str, payload: list[dict]
) -> list[dict]:
    """Call Gemini API with native JSON mode."""
    from google import genai

    response = await client.aio.models.generate_content(
        model=PROVIDER_CONFIGS["gemini"]["model"],
        contents=json.dumps(payload),
        config=genai.types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=PROVIDER_CONFIGS["gemini"]["max_tokens"],
            temperature=0,
        ),
    )
    return _extract_contacts_array(json.loads(response.text))


async def _call_anthropic(
    client: Any, system_prompt: str, payload: list[dict]
) -> list[dict]:
    """Call Claude API with markdown fence stripping."""
    message = await client.messages.create(
        model=PROVIDER_CONFIGS["anthropic"]["model"],
        max_tokens=PROVIDER_CONFIGS["anthropic"]["max_tokens"],
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(payload)}],
        temperature=0,
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1]
        raw = raw.rsplit("```", 1)[0].strip()
    return _extract_contacts_array(json.loads(raw))


async def _call_openai_compat(
    client: Any, system_prompt: str, payload: list[dict], model: str, max_tokens: int
) -> list[dict]:
    """Call OpenAI-compatible API (OpenAI, Groq) with JSON mode."""
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(payload)},
        ],
        response_format={"type": "json_object"},
        temperature=0,
        max_tokens=max_tokens,
    )
    return _extract_contacts_array(json.loads(response.choices[0].message.content))


async def _call_openai(
    client: Any, system_prompt: str, payload: list[dict]
) -> list[dict]:
    cfg = PROVIDER_CONFIGS["openai"]
    return await _call_openai_compat(
        client, system_prompt, payload, cfg["model"], cfg["max_tokens"]
    )


async def _call_groq(
    client: Any, system_prompt: str, payload: list[dict]
) -> list[dict]:
    cfg = PROVIDER_CONFIGS["groq"]
    return await _call_openai_compat(
        client, system_prompt, payload, cfg["model"], cfg["max_tokens"]
    )


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


def _build_provider(name: str) -> CleaningProvider:
    """Build a CleaningProvider for the given name."""
    cfg = PROVIDER_CONFIGS[name]
    max_conc = getattr(settings, cfg["max_concurrent_attr"])

    if name == "gemini":
        from app.utils.gemini_client import get_gemini_client

        return CleaningProvider(
            name=name,
            model=cfg["model"],
            max_concurrent=max_conc,
            get_client=get_gemini_client,
            call=_call_gemini,
        )
    elif name == "anthropic":
        from app.utils.anthropic_client import get_async_client

        return CleaningProvider(
            name=name,
            model=cfg["model"],
            max_concurrent=max_conc,
            get_client=get_async_client,
            call=_call_anthropic,
        )
    elif name == "openai":
        from app.utils.openai_compat_client import get_openai_client

        return CleaningProvider(
            name=name,
            model=cfg["model"],
            max_concurrent=max_conc,
            get_client=get_openai_client,
            call=_call_openai,
        )
    elif name == "groq":
        from app.utils.openai_compat_client import get_groq_client

        return CleaningProvider(
            name=name,
            model=cfg["model"],
            max_concurrent=max_conc,
            get_client=get_groq_client,
            call=_call_groq,
        )
    else:
        raise ValueError(f"Unknown provider: {name}")


def get_enabled_providers(cfg: Any = None) -> list[CleaningProvider]:
    """Return list of providers that have API keys configured."""
    cfg = cfg or settings
    return [
        _build_provider(name)
        for name in PROVIDER_CONFIGS
        if _is_provider_enabled(name, cfg)
    ]


def warm_up_providers() -> None:
    """Eagerly initialize all enabled provider clients.

    Call once before dispatching batches so that slow client init
    (e.g. Gemini Vertex AI writing SA temp file) doesn't eat into
    per-batch timeouts.
    """
    for provider in get_enabled_providers():
        try:
            provider.get_client()
            logger.info("Warmed up provider: %s", provider.name)
        except Exception:
            logger.warning(
                "Failed to warm up provider: %s", provider.name, exc_info=True
            )


# ---------------------------------------------------------------------------
# Dispatch algorithm
# ---------------------------------------------------------------------------

MAX_DISPATCH_ROUNDS = 2
SLOT_ACQUIRE_TIMEOUT = 0.5  # seconds — fail fast so busy providers don't block

# Priority order: fastest/cheapest first, paid APIs as fallback
PROVIDER_PRIORITY = ["groq", "gemini", "anthropic", "openai"]


async def dispatch_batch(batch: list[dict]) -> list[dict]:
    """Route a cleaning batch to the first available provider.

    Tries providers in priority order (Groq → Gemini → others) across
    2 retry rounds with 1s backoff. Falls back to mock cleaner immediately
    if all providers fail — uploads must always complete.
    Returns post-processed (deterministic normalized) results.
    """
    enabled = get_enabled_providers()
    if not enabled:
        logger.warning("No AI providers configured, using mock cleaner")
        return clean_contacts_mock(batch)

    # Sort by priority — unknown providers go last
    priority_map = {name: i for i, name in enumerate(PROVIDER_PRIORITY)}
    enabled.sort(key=lambda p: priority_map.get(p.name, 99))

    payload = _build_cleanup_payload(batch)

    for round_num in range(MAX_DISPATCH_ROUNDS):
        for provider in enabled:
            try:
                used_redis = await acquire_slot(
                    provider.name,
                    max_concurrent=provider.max_concurrent,
                    timeout=SLOT_ACQUIRE_TIMEOUT,
                )
                try:
                    client = provider.get_client()
                    ai_result = await provider.call(
                        client, _CLEANUP_SYSTEM_PROMPT, payload
                    )

                    # Post-process: deterministic normalization on top of AI output
                    cleaned = []
                    for i, ai_fields in enumerate(ai_result):
                        if i < len(batch):
                            cleaned.append(post_process_ai_output(batch[i], ai_fields))

                    logger.info(
                        "Cleaned batch of %d via %s/%s",
                        len(batch),
                        provider.name,
                        provider.model,
                    )
                    return cleaned
                finally:
                    await release_slot(provider.name, used_redis)
            except TimeoutError:
                continue  # provider busy, try next
            except Exception:
                logger.warning(
                    "Provider %s failed, rotating", provider.name, exc_info=True
                )
                continue

        # All providers busy/failed this round — short backoff then retry
        if round_num < MAX_DISPATCH_ROUNDS - 1:
            await asyncio.sleep(1)

    # All rounds exhausted — mock fallback ensures upload always completes
    logger.warning(
        "All providers exhausted after %d rounds, using mock cleaner",
        MAX_DISPATCH_ROUNDS,
    )
    return clean_contacts_mock(batch)
