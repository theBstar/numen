#!/usr/bin/env python3
"""One-time migration script: PostgreSQL entities/edges -> FalkorDB.

Usage:
    python scripts/migrate_to_falkordb.py [--org-id <uuid>]

If --org-id is provided, migrates only that org. Otherwise migrates all orgs.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from uuid import UUID

# Ensure project root is importable
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def migrate_org(org_id: UUID) -> dict[str, int]:
    """Migrate one org's graph data from PostgreSQL to FalkorDB."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.graph.falkor_client import get_org_graph
    from src.graph.indexes import ensure_indexes
    from src.shared.database import async_session as async_session_factory
    from src.shared.models import Edge, Entity

    stats = {"entities": 0, "edges": 0, "skipped_entities": 0, "skipped_edges": 0}

    graph = await get_org_graph(org_id)
    await ensure_indexes(graph)

    async with async_session_factory() as db:
        db: AsyncSession

        # Migrate entities (excluding merged stubs)
        result = await db.execute(
            select(Entity).where(
                Entity.org_id == org_id,
                Entity.merged_into.is_(None),
            )
        )
        entities = list(result.scalars().all())
        logger.info("Org %s: migrating %d entities", org_id, len(entities))

        batch_size = 50
        for i in range(0, len(entities), batch_size):
            batch = entities[i : i + batch_size]
            for entity in batch:
                try:
                    label = entity.type.value.replace("_", "").title()
                    # Ensure label is a valid Cypher identifier
                    if label == "CommitPr":
                        label = "CommitPR"
                    elif label == "ErrorEvent":
                        label = "ErrorEvent"
                    elif label == "MetricSnapshot":
                        label = "MetricSnapshot"

                    source_key = (
                        f"{entity.source.value}:{json.dumps(dict(sorted(entity.source_ids.items())), sort_keys=True)}"
                    )

                    await graph.query(
                        f"CREATE (n:Entity:{label} {{"
                        "id: $id, org_id: $org_id, type: $type, source: $source, source_key: $sk, "
                        "source_ids: $sids, canonical_name: $name, properties: $props, "
                        "created_at: $created, updated_at: $updated"
                        "})",
                        {
                            "id": str(entity.id),
                            "org_id": str(org_id),
                            "type": entity.type.value,
                            "source": entity.source.value,
                            "sk": source_key,
                            "sids": json.dumps(entity.source_ids),
                            "name": entity.canonical_name,
                            "props": json.dumps(entity.properties),
                            "created": entity.created_at.isoformat() if entity.created_at else "",
                            "updated": entity.updated_at.isoformat() if entity.updated_at else "",
                        },
                    )
                    stats["entities"] += 1
                except Exception as exc:
                    logger.warning("Skipped entity %s: %s", entity.id, exc)
                    stats["skipped_entities"] += 1

            logger.info("  entities: %d/%d", min(i + batch_size, len(entities)), len(entities))

        # Migrate edges
        result = await db.execute(select(Edge).where(Edge.org_id == org_id))
        edges = list(result.scalars().all())
        logger.info("Org %s: migrating %d edges", org_id, len(edges))

        for i in range(0, len(edges), batch_size):
            batch = edges[i : i + batch_size]
            for edge in batch:
                try:
                    edge_type_upper = edge.type.value.upper()
                    await graph.query(
                        f"MATCH (a:Entity {{id: $from_id}}), (b:Entity {{id: $to_id}}) "
                        f"CREATE (a)-[r:{edge_type_upper} {{"
                        "id: $eid, type: $etype, weight: $w, confidence: $c, "
                        "evidence: $ev, first_seen_at: $first, last_active_at: $last"
                        "}]->(b)",
                        {
                            "from_id": str(edge.from_entity_id),
                            "to_id": str(edge.to_entity_id),
                            "eid": str(edge.id),
                            "etype": edge.type.value,
                            "w": edge.weight,
                            "c": edge.confidence,
                            "ev": json.dumps(edge.evidence or []),
                            "first": edge.first_seen_at.isoformat() if edge.first_seen_at else "",
                            "last": edge.last_active_at.isoformat() if edge.last_active_at else "",
                        },
                    )
                    stats["edges"] += 1
                except Exception as exc:
                    logger.warning("Skipped edge %s: %s", edge.id, exc)
                    stats["skipped_edges"] += 1

            logger.info("  edges: %d/%d", min(i + batch_size, len(edges)), len(edges))

    logger.info(
        "Org %s migration complete: %d entities, %d edges (%d skipped entities, %d skipped edges)",
        org_id,
        stats["entities"],
        stats["edges"],
        stats["skipped_entities"],
        stats["skipped_edges"],
    )
    return stats


async def main():
    parser = argparse.ArgumentParser(description="Migrate PostgreSQL graph data to FalkorDB")
    parser.add_argument("--org-id", type=str, help="Migrate specific org (UUID)")
    args = parser.parse_args()

    from src.graph.falkor_client import close_falkor

    try:
        if args.org_id:
            org_id = UUID(args.org_id)
            await migrate_org(org_id)
        else:
            # Migrate all orgs
            from sqlalchemy import select

            from src.shared.database import async_session as async_session_factory
            from src.shared.models import Organization

            async with async_session_factory() as db:
                result = await db.execute(select(Organization))
                orgs = list(result.scalars().all())

            logger.info("Found %d organizations to migrate", len(orgs))
            total_stats = {"entities": 0, "edges": 0}
            for org in orgs:
                stats = await migrate_org(org.id)
                total_stats["entities"] += stats["entities"]
                total_stats["edges"] += stats["edges"]

            logger.info(
                "Migration complete: %d total entities, %d total edges across %d orgs",
                total_stats["entities"],
                total_stats["edges"],
                len(orgs),
            )
    finally:
        await close_falkor()


if __name__ == "__main__":
    asyncio.run(main())
