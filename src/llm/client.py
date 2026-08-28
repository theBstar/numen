"""Client wrapper for any OpenAI-compatible LLM endpoint.

Endpoint and model come from src.llm.provider, so the same code path serves
OpenAI, Azure, OpenRouter, and locally-hosted servers like Ollama or vLLM.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import openai

from src.config import settings
from src.llm.provider import build_client_kwargs, resolve_chat_model

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from the LLM API including metadata for tracing."""

    text: str
    model: str = ""
    input_token_count: int = 0
    output_token_count: int = 0
    latency_ms: int = 0


_client: openai.AsyncOpenAI | None = None


def get_client() -> openai.AsyncOpenAI:
    """Return a lazily-initialized singleton client for the configured endpoint."""
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(**build_client_kwargs(settings))
    return _client


async def call_llm(
    system: str,
    user: str,
    max_tokens: int = 2048,
    model: str | None = None,
) -> str:
    """Call the LLM API with retry. Returns only the text content.

    For callers that need metadata (token counts, latency), use
    ``call_llm_with_trace`` instead.
    """
    result = await call_llm_with_trace(system=system, user=user, max_tokens=max_tokens, model=model)
    return result.text


async def call_llm_with_trace(
    system: str,
    user: str,
    max_tokens: int = 2048,
    model: str | None = None,
) -> LLMResponse:
    """Call the OpenAI API with retry (3 attempts, exponential backoff).

    Handles rate-limit and API errors with automatic retries.
    Returns an ``LLMResponse`` with text content and metadata
    (model, token counts, latency) for provenance tracing.
    """
    client = get_client()
    resolved_model = model or resolve_chat_model(settings)
    last_error: Exception | None = None

    for attempt in range(3):
        try:
            start_time = time.monotonic()
            response = await client.chat.completions.create(
                model=resolved_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            choice = response.choices[0] if response.choices else None
            if not choice or not choice.message.content:
                raise ValueError("LLM returned no text content.")

            usage = response.usage
            input_tokens = usage.prompt_tokens if usage else 0
            output_tokens = usage.completion_tokens if usage else 0

            return LLMResponse(
                text=choice.message.content,
                model=response.model or resolved_model,
                input_token_count=input_tokens,
                output_token_count=output_tokens,
                latency_ms=elapsed_ms,
            )

        except openai.RateLimitError as exc:
            last_error = exc
            wait = 2**attempt  # 1s, 2s, 4s
            logger.warning(
                "Rate-limited by the LLM provider (attempt %d/3). Retrying in %ds.",
                attempt + 1,
                wait,
            )
            await asyncio.sleep(wait)

        except openai.APIError as exc:
            last_error = exc
            wait = 2**attempt
            logger.warning(
                "LLM API error (attempt %d/3): %s. Retrying in %ds.",
                attempt + 1,
                exc,
                wait,
            )
            await asyncio.sleep(wait)

    # All retries exhausted
    raise RuntimeError(f"LLM API call failed after 3 attempts: {last_error}") from last_error
