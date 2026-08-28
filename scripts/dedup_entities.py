"""Deduplicate entities in FalkorDB by source_key.

Finds entities that share the same source_key within an org graph,
keeps the oldest (by created_at), re-points edges from duplicates
to the primary, and deletes the duplicates.

Usage:
    python -m scripts.dedup_entities              # dry-run (default)
    python -m scripts.dedup_entities --apply      # actually delete duplicates
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _dedup_org(org_id, *, apply: bool) -> dict:
    """Deduplicate entities in a single org graph. Returns stats."""
    from src.graph.falkor_client import get_org_graph

    graph = await get_org_graph(org_id)
    stats = {
        "org_id": str(org_id),
        "duplicates_found": 0,
        "entities_deleted": 0,
        "edges_repointed": 0,
    }

    # Find all entities grouped by source_key
    result = await graph.query(
        "MATCH (n:Entity) WHERE n.source_key IS NOT NULL RETURN n.source_key AS sk, collect(n) AS nodes ORDER BY sk"
    )

    for row in result.result_set:
        source_key = row[0]
        nodes = row[1]

        if len(nodes) <= 1:
            continue

        # Parse nodes into dicts
        parsed = []
        for node in nodes:
            props = dict(node.properties) if hasattr(node, "properties") else dict(node)
            parsed.append(props)

        # Sort by created_at ascending - keep the oldest
        parsed.sort(key=lambda p: p.get("created_at", ""))
        primary = parsed[0]
        duplicates = parsed[1:]

        primary_id = primary.get("id")
        dup_count = len(duplicates)
        stats["duplicates_found"] += dup_count

        logger.info(
            "  source_key=%s  primary=%s  duplicates=%d  type=%s  name=%s",
            source_key[:60],
            primary_id[:8] if primary_id else "?",
            dup_count,
            primary.get("type", "?"),
            (primary.get("canonical_name") or "")[:40],
        )

        if not apply:
            continue

        for dup in duplicates:
            dup_id = dup.get("id")
            if not dup_id:
                continue

            # Re-point outgoing edges from duplicate to primary
            repoint_out = await graph.query(
                "MATCH (dup:Entity {id: $dup_id})-[r]->(target:Entity) "
                "WHERE target.id <> $primary_id "
                "RETURN type(r) AS rtype, r, target.id AS tid",
                {"dup_id": dup_id, "primary_id": primary_id},
            )
            for erow in repoint_out.result_set:
                rtype = erow[0]
                tid = erow[2]
                # Check if primary already has this edge
                existing = await graph.query(
                    f"MATCH (a:Entity {{id: $pid}})-[r:{rtype}]->(b:Entity {{id: $tid}}) RETURN r LIMIT 1",
                    {"pid": primary_id, "tid": tid},
                )
                if not existing.result_set:
                    # Create the edge from primary
                    edge_props = dict(erow[1].properties) if hasattr(erow[1], "properties") else {}
                    props_json = json.dumps(edge_props)
                    await graph.query(
                        f"MATCH (a:Entity {{id: $pid}}), (b:Entity {{id: $tid}}) "
                        f"CREATE (a)-[r:{rtype}]->(b) "
                        "SET r = $props RETURN r",
                        {"pid": primary_id, "tid": tid, "props": props_json},
                    )
                    stats["edges_repointed"] += 1

            # Re-point incoming edges to duplicate -> primary
            repoint_in = await graph.query(
                "MATCH (source:Entity)-[r]->(dup:Entity {id: $dup_id}) "
                "WHERE source.id <> $primary_id "
                "RETURN type(r) AS rtype, r, source.id AS sid",
                {"dup_id": dup_id, "primary_id": primary_id},
            )
            for erow in repoint_in.result_set:
                rtype = erow[0]
                sid = erow[2]
                existing = await graph.query(
                    f"MATCH (a:Entity {{id: $sid}})-[r:{rtype}]->(b:Entity {{id: $pid}}) RETURN r LIMIT 1",
                    {"sid": sid, "pid": primary_id},
                )
                if not existing.result_set:
                    edge_props = dict(erow[1].properties) if hasattr(erow[1], "properties") else {}
                    props_json = json.dumps(edge_props)
                    await graph.query(
                        f"MATCH (a:Entity {{id: $sid}}), (b:Entity {{id: $pid}}) "
                        f"CREATE (a)-[r:{rtype}]->(b) "
                        "SET r = $props RETURN r",
                        {"sid": sid, "pid": primary_id, "props": props_json},
                    )
                    stats["edges_repointed"] += 1

            # Delete the duplicate node (and its edges)
            await graph.query(
                "MATCH (n:Entity {id: $id}) DETACH DELETE n",
                {"id": dup_id},
            )
            stats["entities_deleted"] += 1

    return stats


async def main():
    from sqlalchemy import select

    from src.shared.database import async_session
    from src.shared.models import Organization

    apply = "--apply" in sys.argv

    if apply:
        logger.info("=== APPLY MODE - will delete duplicates ===")
    else:
        logger.info("=== DRY RUN - pass --apply to actually delete ===")

    async with async_session() as db:
        result = await db.execute(select(Organization.id))
        org_ids = [row[0] for row in result.fetchall()]

    logger.info("Found %d organizations", len(org_ids))
    total_stats = {"duplicates_found": 0, "entities_deleted": 0, "edges_repointed": 0}

    for org_id in org_ids:
        logger.info("Processing org %s ...", org_id)
        stats = await _dedup_org(org_id, apply=apply)
        for k in total_stats:
            total_stats[k] += stats.get(k, 0)

    logger.info("=== Summary ===")
    logger.info("  Duplicates found: %d", total_stats["duplicates_found"])
    logger.info("  Entities deleted: %d", total_stats["entities_deleted"])
    logger.info("  Edges repointed: %d", total_stats["edges_repointed"])

    if not apply and total_stats["duplicates_found"] > 0:
        logger.info("  Run with --apply to delete duplicates")


if __name__ == "__main__":
    asyncio.run(main())
