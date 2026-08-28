"""Provider adapter for any OpenAI-compatible LLM endpoint.

Numen speaks the OpenAI wire protocol, which every major serving stack now
implements. Pointing `LLM_BASE_URL` at Ollama, vLLM, LiteLLM, OpenRouter, or
Azure is therefore all it takes to run Numen without sending a single token
to a third party - the reason most companies self-host this category at all.

The legacy `OPENAI_*` settings stay honoured so existing installs keep
working after an upgrade.
"""

from __future__ import annotations

from typing import Any

# Chat model used when the operator sets only an API key.
DEFAULT_CHAT_MODEL = "gpt-4o-mini"

# Embedding model and the width of the FalkorDB vector index built for it.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSIONS = 1536

# Local servers authenticate by network reachability, but the OpenAI SDK
# refuses to construct a client with an empty key.
KEYLESS_PLACEHOLDER = "not-needed"


class LLMConfigurationError(RuntimeError):
    """Raised when no usable LLM credentials or endpoint are configured."""


def resolve_base_url(settings: Any) -> str | None:
    """Return the configured endpoint, or None to use the OpenAI default."""
    base_url = (getattr(settings, "llm_base_url", "") or "").strip()
    return base_url.rstrip("/") or None


def resolve_api_key(settings: Any) -> str:
    """Return the API key, preferring LLM_API_KEY over the legacy OPENAI_API_KEY."""
    key = (getattr(settings, "llm_api_key", "") or "").strip()
    if not key:
        key = (getattr(settings, "openai_api_key", "") or "").strip()
    if key:
        return key

    # A custom endpoint implies a local or proxied server that may not want a key.
    if resolve_base_url(settings):
        return KEYLESS_PLACEHOLDER

    raise LLMConfigurationError(
        "No LLM credentials configured. Set LLM_API_KEY for a hosted provider, "
        "or set LLM_BASE_URL to point at a local OpenAI-compatible server "
        "such as Ollama (http://localhost:11434/v1)."
    )


def resolve_chat_model(settings: Any) -> str:
    """Return the chat/completion model name."""
    model = (getattr(settings, "llm_model", "") or "").strip()
    if not model:
        model = (getattr(settings, "openai_model", "") or "").strip()
    return model or DEFAULT_CHAT_MODEL


def resolve_embedding_model(settings: Any) -> str:
    """Return the embedding model name."""
    model = (getattr(settings, "embedding_model", "") or "").strip()
    return model or DEFAULT_EMBEDDING_MODEL


def resolve_embedding_dimensions(settings: Any) -> int:
    """Return the embedding width.

    Must match the FalkorDB vector index; changing it requires a reindex.
    """
    dimensions = getattr(settings, "embedding_dimensions", 0) or 0
    return int(dimensions) or DEFAULT_EMBEDDING_DIMENSIONS


def is_llm_configured(settings: Any) -> bool:
    """Whether an LLM is reachable, for features that degrade without one."""
    try:
        resolve_api_key(settings)
    except LLMConfigurationError:
        return False
    return True


def build_client_kwargs(settings: Any) -> dict[str, Any]:
    """Build constructor kwargs shared by the OpenAI and LangChain clients."""
    kwargs: dict[str, Any] = {"api_key": resolve_api_key(settings)}
    base_url = resolve_base_url(settings)
    if base_url:
        kwargs["base_url"] = base_url
    return kwargs
