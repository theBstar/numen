"""Context graph extraction - TrustGraph-inspired pattern.

Instead of dumping the full org graph, extract query-specific subgraphs
using vector similarity + graph expansion. This produces compact, relevant
context for LLM consumption.

Key insight from TrustGraph: "Context graphs achieve 70% token reduction
while preserving essential information through dense representation."
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.graph.falkor_client import get_org_graph
from src.graph.falkor_repository import _edge_to_dict, _node_to_dict

logger = logging.getLogger(__name__)


async def extract_context_graph(
    org_id: UUID,
    query: str,
    *,
    max_entities: int = 50,
    expansion_hops: int = 2,
    vector_k: int = 10,
) -> dict:
    """Extract a query-specific subgraph for LLM context.

    TrustGraph dual-representation pattern:
    1. Vector search for entry points (FalkorDB native HNSW)
    2. Graph expansion via Cypher traversal
    3. Return compact subgraph with relevance scores

    Returns::

        {
            "entities": [dict, ...],
            "edges": [dict, ...],
            "entry_scores": {entity_id: float, ...},
        }
    """
    graph = await get_org_graph(org_id)

    # Step 1: Try vector search for entry points
    entry_entities = []
    entry_scores: dict[str, float] = {}

    try:
        # Embed the query (assumes embedding function is available)
        from src.graph._embedding import embed_text

        query_embedding = await embed_text(query)

        vector_result = await graph.query(
            "CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($emb)) "
            "YIELD node, score "
            "RETURN node, score",
            {"emb": query_embedding, "k": vector_k},
        )

        for row in vector_result.result_set:
            node = _node_to_dict(row[0])
            score = row[1]
            entry_entities.append(node)
            nid = node.get("id")
            if nid:
                entry_scores[nid] = score

    except (ImportError, Exception) as exc:
        # Vector search not available - fall back to text search
        logger.debug("Vector search unavailable, falling back to text: %s", exc)
        text_result = await graph.query(
            "MATCH (n:Entity) WHERE toLower(n.canonical_name) CONTAINS toLower($q) RETURN n LIMIT $k",
            {"q": query, "k": vector_k},
        )
        for row in text_result.result_set:
            node = _node_to_dict(row[0])
            entry_entities.append(node)
            nid = node.get("id")
            if nid:
                entry_scores[nid] = 1.0

    if not entry_entities:
        return {"entities": [], "edges": [], "entry_scores": {}}

    # Step 2: Graph expansion from entry points
    entry_ids = [e.get("id") for e in entry_entities if e.get("id")]

    expansion_result = await graph.query(
        "MATCH (entry:Entity)-[r*1..$hops]-(related:Entity) WHERE entry.id IN $ids RETURN DISTINCT related",
        {"ids": entry_ids, "hops": expansion_hops},
    )

    # Collect all entities (entries + expanded)
    entity_map: dict[str, dict] = {}
    for e in entry_entities:
        eid = e.get("id")
        if eid:
            entity_map[eid] = e

    for row in expansion_result.result_set:
        node = _node_to_dict(row[0])
        nid = node.get("id")
        if nid and nid not in entity_map:
            entity_map[nid] = node

    # Trim to max_entities (prioritize entry nodes + most connected)
    if len(entity_map) > max_entities:
        # Keep all entry nodes, then sort remainder by whether they have scores
        entries_first = [eid for eid in entity_map if eid in entry_scores]
        rest = [eid for eid in entity_map if eid not in entry_scores]
        keep_ids = set(entries_first[:max_entities])
        remaining_slots = max_entities - len(keep_ids)
        keep_ids.update(rest[:remaining_slots])
        entity_map = {k: v for k, v in entity_map.items() if k in keep_ids}

    # Step 3: Get edges between visible entities
    all_ids = list(entity_map.keys())
    edges: list[dict] = []

    if all_ids:
        edge_result = await graph.query(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rtype",
            {"ids": all_ids},
        )
        for row in edge_result.result_set:
            e = _edge_to_dict(row[0])
            e["from_entity_id"] = row[1]
            e["to_entity_id"] = row[2]
            e["type"] = row[3].lower() if row[3] else e.get("type", "")
            edges.append(e)

    return {
        "entities": list(entity_map.values()),
        "edges": edges,
        "entry_scores": entry_scores,
    }


async def context_to_text(context: dict) -> str:
    """Convert a context graph to a text representation for LLM consumption.

    TrustGraph pattern: dense, structured text representation that fits
    in LLM context windows efficiently.
    """
    lines = ["# Context Graph\n"]

    # Entities section
    lines.append("## Entities\n")
    for entity in context.get("entities", []):
        etype = entity.get("type", "unknown")
        name = entity.get("canonical_name", "unnamed")
        eid = entity.get("id", "?")
        score = context.get("entry_scores", {}).get(eid, "")
        score_str = f" (relevance: {score:.2f})" if score else ""
        lines.append(f"- [{etype}] {name}{score_str}")

    # Relationships section
    lines.append("\n## Relationships\n")
    entity_names = {e.get("id"): e.get("canonical_name", "?") for e in context.get("entities", [])}
    for edge in context.get("edges", []):
        from_name = entity_names.get(edge.get("from_entity_id"), "?")
        to_name = entity_names.get(edge.get("to_entity_id"), "?")
        rel_type = edge.get("type", "related_to")
        lines.append(f"- {from_name} --[{rel_type}]--> {to_name}")

    return "\n".join(lines)
