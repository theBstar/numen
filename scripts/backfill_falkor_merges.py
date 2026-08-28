#!/usr/bin/env python3
"""Replay pre-migration Postgres merge state into FalkorDB.

The original PG->FalkorDB migration (scripts/migrate_to_falkordb.py) skipped any
Entity rows with merged_into IS NOT NULL. As a result, entities that were merged
before the cutover still appear in FalkorDB read paths. This script re-creates
those merged stubs in FalkorDB with their merged_into pointer set, so list/count
queries (which filter on merged_into IS NULL) hide them correctly.

Idempotent: re-running is a no-op. Read-only on Postgres; additive on FalkorDB.

Usage:
    python scripts/backfill_falkor_merges.py [--org-id <uuid>]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from uuid import UUID

sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _label_for(entity_type_value: str) -> str:
    """Mirror the label mapping used in migrate_to_falkordb.py and falkor_repository.py."""
    label = entity_type_value.replace("_", "").title()
    if label == "CommitPr":
        return "CommitPR"
    return label


def _resolve_terminal_primary(entity_id: UUID, merge_map: dict[UUID, UUID]) -> UUID:
    """Follow the merged_into chain to the final non-merged primary."""
    seen: set[UUID] = set()
    current = entity_id
    while current in merge_map:
        if current in seen:
            logger.warning("Cycle detected in merge chain at %s; stopping", current)
            break
        seen.add(current)
        current = merge_map[current]
    return current


async def backfill_org(org_id: UUID) -> dict[str, int]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.graph.falkor_client import get_org_graph
    from src.shared.database import async_session as async_session_factory
    from src.shared.models import Entity

    stats = {"backfilled": 0, "already_present": 0, "skipped": 0, "errors": 0}

    graph = await get_org_graph(org_id)

    async with async_session_factory() as db:
        db: AsyncSession

        result = await db.execute(
            select(Entity).where(
                Entity.org_id == org_id,
                Entity.merged_into.is_not(None),
            )
        )
        merged_entities = list(result.scalars().all())

    if not merged_entities:
        logger.info("Org %s: no merged entities to backfill", org_id)
        return stats

    merge_map: dict[UUID, UUID] = {e.id: e.merged_into for e in merged_entities if e.merged_into}

    logger.info("Org %s: %d merged entities to backfill", org_id, len(merged_entities))

    for entity in merged_entities:
        try:
            existing = await graph.query(
                "MATCH (n:Entity {id: $id}) RETURN n LIMIT 1",
                {"id": str(entity.id)},
            )
            if existing.result_set:
                node = existing.result_set[0][0]
                props = dict(node.properties) if hasattr(node, "properties") else dict(node)
                if props.get("merged_into"):
                    stats["already_present"] += 1
                    continue
                terminal = _resolve_terminal_primary(entity.merged_into, merge_map)
                await graph.query(
                    "MATCH (n:Entity {id: $id}) SET n.merged_into = $mid",
                    {"id": str(entity.id), "mid": str(terminal)},
                )
                stats["backfilled"] += 1
                continue

            terminal_primary = _resolve_terminal_primary(entity.merged_into, merge_map)

            label = _label_for(entity.type.value)
            source_key = f"{entity.source.value}:{json.dumps(dict(sorted(entity.source_ids.items())), sort_keys=True)}"

            await graph.query(
                f"CREATE (n:Entity:{label} {{"
                "id: $id, org_id: $org_id, type: $type, source: $source, source_key: $sk, "
                "source_ids: $sids, canonical_name: $name, properties: $props, "
                "created_at: $created, updated_at: $updated, merged_into: $mid"
                "})",
                {
                    "id": str(entity.id),
                    "org_id": str(org_id),
                    "type": entity.type.value,
                    "source": entity.source.value,
                    "sk": source_key,
                    "sids": json.dumps(entity.source_ids or {}),
                    "name": entity.canonical_name,
                    "props": json.dumps(entity.properties or {}),
                    "created": entity.created_at.isoformat() if entity.created_at else "",
                    "updated": entity.updated_at.isoformat() if entity.updated_at else "",
                    "mid": str(terminal_primary),
                },
            )
            stats["backfilled"] += 1
        except Exception as exc:
            logger.warning("Failed to backfill entity %s: %s", entity.id, exc)
            stats["errors"] += 1

    logger.info(
        "Org %s backfill complete: %d backfilled, %d already present, %d errors",
        org_id,
        stats["backfilled"],
        stats["already_present"],
        stats["errors"],
    )
    return stats


async def main():
    parser = argparse.ArgumentParser(
        description="Backfill pre-migration merges from Postgres into FalkorDB",
    )
    parser.add_argument("--org-id", type=str, help="Backfill specific org (UUID)")
    args = parser.parse_args()

    from src.graph.falkor_client import close_falkor

    try:
        if args.org_id:
            await backfill_org(UUID(args.org_id))
        else:
            from sqlalchemy import select

            from src.shared.database import async_session as async_session_factory
            from src.shared.models import Organization

            async with async_session_factory() as db:
                result = await db.execute(select(Organization))
                orgs = list(result.scalars().all())

            totals = {"backfilled": 0, "already_present": 0, "errors": 0}
            for org in orgs:
                s = await backfill_org(org.id)
                for k in totals:
                    totals[k] += s[k]

            logger.info(
                "All orgs complete: %d backfilled, %d already present, %d errors",
                totals["backfilled"],
                totals["already_present"],
                totals["errors"],
            )
    finally:
        await close_falkor()


if __name__ == "__main__":
    asyncio.run(main())
