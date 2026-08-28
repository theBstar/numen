"""Product wiki utilities - graph visualization, text extraction, cache.

The feature-centric wiki logic lives in wiki_generator.py. This module
provides the graph visualization endpoint, shared text extraction helpers,
and Redis cache management.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.shared.models import WikiConcept, WikiFeature

logger = logging.getLogger(__name__)

WIKI_CACHE_TTL = 300  # 5 minutes


def _get_redis() -> redis.Redis:
    """Create a Redis async client from application settings."""
    return redis.from_url(settings.redis_url, decode_responses=True)


def _wiki_graph_key(org_id: UUID) -> str:
    return f"wiki:{org_id}:graph"


def _extract_text_from_content(content: dict | None) -> str:
    """Recursively extract plain text from TipTap JSON content."""
    if not content:
        return ""

    parts: list[str] = []

    if content.get("type") == "text":
        text = content.get("text", "")
        if text:
            parts.append(text)

    for child in content.get("content", []):
        if isinstance(child, dict):
            parts.append(_extract_text_from_content(child))

    return " ".join(parts).strip()


# ── Feature-centric graph view ────────────────────────────────────


async def get_wiki_graph(db: AsyncSession, org_id: UUID) -> dict:
    """Get the wiki as a feature-centric graph for visualization.

    Nodes: features (purple), PRDs (blue), concepts (orange)
    Edges: feature->PRD (references), feature->concept (uses)
    """
    # Check cache
    client = _get_redis()
    try:
        cached = await client.get(_wiki_graph_key(org_id))
        if cached:
            return json.loads(cached)
    except Exception:
        pass
    finally:
        await client.aclose()

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    # 1. Features as primary nodes
    features_result = await db.execute(
        select(WikiFeature).where(WikiFeature.org_id == org_id).order_by(WikiFeature.position)
    )
    for wf in features_result.scalars().all():
        fid = str(wf.id)
        seen_ids.add(fid)
        nodes.append(
            {
                "id": fid,
                "type": "feature",
                "label": wf.title,
                "status": wf.status,
                "domain_group": wf.domain_group,
            }
        )

        # Feature -> PRD edges
        for ref in wf.prd_references or []:
            prd_eid = ref.get("entity_id", "")
            prd_title = ref.get("prd_title", "")
            if not prd_eid:
                continue

            # Add PRD node if not seen
            if prd_eid not in seen_ids:
                seen_ids.add(prd_eid)
                nodes.append(
                    {
                        "id": prd_eid,
                        "type": "prd",
                        "label": prd_title,
                        "status": "",
                    }
                )

            edges.append(
                {
                    "source": fid,
                    "target": prd_eid,
                    "type": "references",
                    "label": "from PRD",
                }
            )

        # Feature -> Concept edges
        for cid in wf.concept_ids or []:
            if cid not in seen_ids:
                # Will be added when we iterate concepts
                pass
            edges.append(
                {
                    "source": fid,
                    "target": str(cid),
                    "type": "uses_concept",
                    "label": "uses",
                }
            )

    # 2. Concepts as secondary nodes
    concepts_result = await db.execute(select(WikiConcept).where(WikiConcept.org_id == org_id))
    for wc in concepts_result.scalars().all():
        cid = str(wc.id)
        if cid not in seen_ids:
            seen_ids.add(cid)
            nodes.append(
                {
                    "id": cid,
                    "type": "concept",
                    "label": wc.term,
                    "status": "",
                }
            )

    result = {"nodes": nodes, "edges": edges}

    # Cache
    client = _get_redis()
    try:
        await client.set(
            _wiki_graph_key(org_id),
            json.dumps(result),
            ex=WIKI_CACHE_TTL,
        )
    except Exception:
        pass
    finally:
        await client.aclose()

    return result


# ── Cache invalidation ─────────────────────────────────────────────


async def invalidate_wiki_cache(org_id: UUID) -> None:
    """Invalidate wiki cache for an org. Called by PRD event handlers."""
    client = _get_redis()
    try:
        # Delete all wiki keys for this org
        pattern = f"wiki:{org_id}:*"
        cursor: int | str = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await client.delete(*keys)
            if cursor == 0:
                break
        logger.debug("Invalidated wiki cache for org=%s", org_id)
    except Exception:
        logger.debug("Failed to invalidate wiki cache for org=%s", org_id)
    finally:
        await client.aclose()
