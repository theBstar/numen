#!/usr/bin/env python3
"""Restore archived PRDs by flipping prd_status ARCHIVED -> DRAFT.

Historical soft-deletes (delete_prd) overwrote prd_status with "ARCHIVED",
hiding PRDs from the list endpoint while the derived Wiki cache kept showing
them. This script scans every org for archived DOCUMENT entities and reverts
them to DRAFT, then invalidates the wiki cache so future reads are consistent.

Idempotent. Goes direct through update_entity (not update_prd) to avoid
emitting cosmetic PrdVersion snapshots for a bulk data repair.

Usage:
    python scripts/restore_archived_prds.py                 # dry run, all orgs
    python scripts/restore_archived_prds.py --apply
    python scripts/restore_archived_prds.py --org-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from uuid import UUID

sys.path.insert(0, ".")

from sqlalchemy import select  # noqa: E402

from src.graph.falkor_repository import list_entities, update_entity  # noqa: E402
from src.prd.wiki import invalidate_wiki_cache  # noqa: E402
from src.shared.database import async_session  # noqa: E402
from src.shared.models import Organization  # noqa: E402
from src.shared.types import EntityType, PrdNodeType, PrdStatus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


PRD_NODE_TYPES = {
    PrdNodeType.DOCUMENT.value,
    PrdNodeType.FOLDER.value,
    PrdNodeType.IMAGE.value,
}


async def restore_org(org_id: UUID, apply: bool) -> tuple[int, int]:
    """Restore archived PRDs for one org. Returns (scanned, restored)."""
    scanned = 0
    restored = 0

    async with async_session() as db:
        entities = await list_entities(
            db,
            org_id,
            entity_type=EntityType.DOCUMENT,
            limit=10000,
        )

        for entity in entities:
            scanned += 1
            props = entity.properties
            if isinstance(props, str):
                props = json.loads(props)

            if props.get("node_type") not in PRD_NODE_TYPES:
                continue
            if props.get("prd_status") != PrdStatus.ARCHIVED.value:
                continue

            entity_id = UUID(str(entity.id))
            title = props.get("canonical_name") or props.get("title") or "<untitled>"

            if not apply:
                logger.info(
                    "DRY RUN org=%s entity=%s title=%r would restore ARCHIVED -> DRAFT",
                    org_id,
                    entity_id,
                    title,
                )
                restored += 1
                continue

            new_props = dict(props)
            new_props["prd_status"] = PrdStatus.DRAFT.value

            await update_entity(
                db,
                entity_id,
                org_id=org_id,
                properties=new_props,
                merge_properties=False,
            )
            await db.commit()
            restored += 1
            logger.info(
                "Restored org=%s entity=%s title=%r", org_id, entity_id, title
            )

    if apply and restored:
        await invalidate_wiki_cache(org_id)
        logger.info("Invalidated wiki cache for org=%s", org_id)

    return scanned, restored


async def run(target_org_id: UUID | None, apply: bool) -> None:
    async with async_session() as session:
        if target_org_id is not None:
            org_ids = [target_org_id]
        else:
            result = await session.execute(select(Organization.id))
            org_ids = [row[0] for row in result.fetchall()]

    total_scanned = 0
    total_restored = 0
    for org_id in org_ids:
        try:
            scanned, restored = await restore_org(org_id, apply)
        except Exception:
            logger.exception("Failed to process org=%s", org_id)
            continue
        total_scanned += scanned
        total_restored += restored
        logger.info(
            "org=%s scanned=%d restored=%d", org_id, scanned, restored
        )

    logger.info(
        "Done. orgs=%d scanned=%d restored=%d apply=%s",
        len(org_ids),
        total_scanned,
        total_restored,
        apply,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org-id", type=UUID, default=None, help="Limit to one org")
    parser.add_argument(
        "--apply", action="store_true", help="Perform writes (default: dry run)"
    )
    args = parser.parse_args()
    asyncio.run(run(target_org_id=args.org_id, apply=args.apply))


if __name__ == "__main__":
    main()
