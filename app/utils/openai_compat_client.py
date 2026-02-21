"""OpenAI-compatible client singletons.

Provides lazy-initialized async and sync clients for OpenAI, Groq, and DeepSeek.
All three use the openai SDK — Groq and DeepSeek via base_url override.
"""

from openai import AsyncOpenAI, OpenAI

from app.config import settings

_openai_client: AsyncOpenAI | None = None
_groq_client: AsyncOpenAI | None = None
_groq_sync_client: OpenAI | None = None
_deepseek_client: AsyncOpenAI | None = None


def _build_openai_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=120.0, max_retries=1)


def _build_groq_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=120.0,
        max_retries=1,
    )


def _build_deepseek_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com",
        timeout=120.0,
        max_retries=1,
    )


def get_openai_client() -> AsyncOpenAI:
    """Lazy singleton OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = _build_openai_client()
    return _openai_client


def get_groq_client() -> AsyncOpenAI:
    """Lazy singleton Groq async client (OpenAI-compatible)."""
    global _groq_client
    if _groq_client is None:
        _groq_client = _build_groq_client()
    return _groq_client


def get_groq_sync_client() -> OpenAI:
    """Lazy singleton Groq sync client (OpenAI-compatible)."""
    global _groq_sync_client
    if _groq_sync_client is None:
        _groq_sync_client = OpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            timeout=120.0,
            max_retries=1,
        )
    return _groq_sync_client


def get_deepseek_client() -> AsyncOpenAI:
    """Lazy singleton DeepSeek client (OpenAI-compatible)."""
    global _deepseek_client
    if _deepseek_client is None:
        _deepseek_client = _build_deepseek_client()
    return _deepseek_client
