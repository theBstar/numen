"""Embedding helper for context graph vector search.

Provides text-to-vector embedding for FalkorDB vector index queries.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_client: Any = None


async def embed_text(text: str) -> list[float]:
    """Embed text using the configured OpenAI-compatible endpoint.

    The vector width must match the graph's vector index - see
    EMBEDDING_DIMENSIONS. Raises if embedding is unavailable; callers
    degrade to non-vector search.
    """
    global _client

    try:
        from openai import AsyncOpenAI

        from src.config import settings
        from src.llm.provider import build_client_kwargs, resolve_embedding_model

        if _client is None:
            _client = AsyncOpenAI(**build_client_kwargs(settings))

        response = await _client.embeddings.create(
            model=resolve_embedding_model(settings),
            input=text,
        )
        return response.data[0].embedding

    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        raise
