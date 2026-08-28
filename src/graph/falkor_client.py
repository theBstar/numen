"""Async FalkorDB client with per-org graph isolation.

Each organization gets its own isolated FalkorDB graph, providing native
multi-tenancy without org_id filtering in queries.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse
from uuid import UUID

from falkordb.asyncio import FalkorDB

from src.config import settings

logger = logging.getLogger(__name__)

_client: FalkorDB | None = None


async def get_falkor() -> FalkorDB:
    """Return the singleton async FalkorDB client."""
    global _client
    if _client is None:
        parsed = urlparse(settings.falkordb_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        _client = FalkorDB(host=host, port=port)
        logger.info("FalkorDB client connected to %s:%s", host, port)
    return _client


async def get_org_graph(org_id: UUID):
    """Get the isolated FalkorDB graph for an organization.

    Each org's graph is named ``org_<hex>``, providing full data isolation
    at the database level - no org_id filtering needed in Cypher queries.
    """
    client = await get_falkor()
    graph_name = f"org_{org_id.hex}"
    return client.select_graph(graph_name)


async def close_falkor() -> None:
    """Close the FalkorDB client connection. Call on app shutdown."""
    global _client
    if _client is not None:
        try:
            await _client.aclose()
        except AttributeError:
            pass  # Older versions may not have aclose
        _client = None
        logger.info("FalkorDB client closed")
