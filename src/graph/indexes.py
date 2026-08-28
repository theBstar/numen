"""FalkorDB index management - property and vector indexes.

Run ``ensure_indexes`` once per org graph on creation or migration.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def ensure_indexes(graph) -> None:
    """Create property and vector indexes on an org graph.

    Safe to call multiple times - FalkorDB ignores duplicate index creation.
    """
    index_queries = [
        # Property indexes for fast entity lookups
        "CREATE INDEX FOR (n:Entity) ON (n.id)",
        "CREATE INDEX FOR (n:Entity) ON (n.source_key)",
        "CREATE INDEX FOR (n:Entity) ON (n.type)",
        "CREATE INDEX FOR (n:Entity) ON (n.canonical_name)",
        "CREATE INDEX FOR (n:Person) ON (n.email)",
        "CREATE INDEX FOR (n:Person) ON (n.github_username)",
        "CREATE INDEX FOR (n:Person) ON (n.slack_id)",
        "CREATE INDEX FOR (n:Task) ON (n.status)",
    ]

    for query in index_queries:
        try:
            await graph.query(query)
        except Exception as exc:
            # Index may already exist - that's fine
            if "already indexed" not in str(exc).lower():
                logger.warning("Index creation warning: %s - %s", query, exc)

    # Vector index for semantic search (TrustGraph dual-representation pattern)
    try:
        await graph.query(
            "CREATE VECTOR INDEX FOR (n:Entity) ON (n.embedding) "
            "OPTIONS {dimension: 1536, similarityFunction: 'cosine'}"
        )
    except Exception as exc:
        if "already indexed" not in str(exc).lower():
            logger.warning("Vector index creation warning: %s", exc)

    logger.info("FalkorDB indexes ensured for graph")
