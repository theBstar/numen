#!/usr/bin/env python3
"""Purge Postgres rows whose PRD Entity no longer exists in FalkorDB.

Pre-cascade delete_prd left Postgres artifacts behind when the FalkorDB
graph got wiped or PRDs were hard-deleted via other paths. This script
finds every PrdBlock / PrdVersion / PrdComment / PrdReaction / PrdReview /
PrdMedia / PrdAlignmentCheck row whose entity_id has no matching DOCUMENT
Entity in the org's FalkorDB graph, and removes the rows.

Also prunes WikiFeature / WikiConcept / WikiProductSummary JSONB references
for the orphaned entity_ids and invalidates the wiki cache.

PrdMedia S3 blobs are best-effort deleted - failures are logged. Postgres
is the source of truth for cleanup success; a leaked blob is cheap.

Usage:
    python scripts/purge_orphaned_prd_rows.py                # dry run, all orgs
    python scripts/purge_orphaned_prd_rows.py --apply
    python scripts/purge_orphaned_prd_rows.py --org-id <uuid> --apply
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID

sys.path.insert(0, ".")

from sqlalchemy import func, select  # noqa: E402

from src.graph.falkor_repository import list_entities  # noqa: E402
from src.prd.deletion import _prune_wiki_refs  # noqa: E402
from src.prd.wiki import invalidate_wiki_cache  # noqa: E402
from src.shared.database import async_session  # noqa: E402
from src.shared.models import (  # noqa: E402
    Organization,
    PrdAlignmentCheck,
    PrdBlock,
    PrdComment,
    PrdMedia,
    PrdReaction,
    PrdReview,
    PrdVersion,
)
from src.shared.types import EntityType  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def _graph_entity_ids(org_id: UUID) -> set[UUID]:
    """All DOCUMENT entity_ids present in the org's FalkorDB graph."""
    async with async_session() as db:
        entities = await list_entities(
            db,
            org_id,
            entity_type=EntityType.DOCUMENT,
            limit=10000,
        )
    ids: set[UUID] = set()
    for e in entities:
        try:
            ids.add(UUID(str(e.id)))
        except (TypeError, ValueError):
            continue
    return ids


async def _orphaned_entity_ids(
    org_id: UUID, graph_ids: set[UUID]
) -> dict[str, set[UUID]]:
    """Per-table orphan sets. Returns {table_name: {entity_ids_not_in_graph}}."""
    tables = {
        "prd_blocks": (PrdBlock, PrdBlock.entity_id),
        "prd_versions": (PrdVersion, PrdVersion.entity_id),
        "prd_comments": (PrdComment, PrdComment.entity_id),
        "prd_reviews": (PrdReview, PrdReview.entity_id),
        "prd_media": (PrdMedia, PrdMedia.entity_id),
        "prd_alignment_checks": (PrdAlignmentCheck, PrdAlignmentCheck.prd_entity_id),
    }
    result: dict[str, set[UUID]] = {}
    async with async_session() as db:
        for name, (model, col) in tables.items():
            rows = (
                await db.execute(
                    select(col).where(model.org_id == org_id).distinct()
                )
            ).scalars().all()
            orphans = {eid for eid in rows if eid not in graph_ids}
            result[name] = orphans
    return result


async def _delete_s3_blobs(storage_keys: list[str]) -> int:
    """Delete S3 objects for orphaned PrdMedia rows. Returns success count."""
    if not storage_keys:
        return 0
    try:
        import aioboto3

        from src.prd.media import S3_BUCKET, _build_s3_client_kwargs
    except Exception:
        logger.warning("S3 config unavailable - skipping blob delete")
        return 0

    try:
        kwargs = _build_s3_client_kwargs()
    except ValueError as e:
        logger.warning("S3 credentials not configured: %s - skipping blob delete", e)
        return 0

    deleted = 0
    session = aioboto3.Session()
    async with session.client(**kwargs) as s3:
        for key in storage_keys:
            try:
                await s3.delete_object(Bucket=S3_BUCKET, Key=key)
                deleted += 1
            except Exception:
                logger.exception("Failed to delete S3 blob %s", key)
    return deleted


async def purge_org(org_id: UUID, apply: bool) -> dict:
    """Purge orphaned PRD rows for one org. Returns a summary dict."""
    graph_ids = await _graph_entity_ids(org_id)
    per_table = await _orphaned_entity_ids(org_id, graph_ids)

    all_orphans = set().union(*per_table.values())
    if not all_orphans:
        logger.info("org=%s no orphaned PRD data", org_id)
        return {"org_id": str(org_id), "orphaned_entity_ids": 0}

    logger.info(
        "org=%s graph_entities=%d orphaned_entity_ids=%d",
        org_id,
        len(graph_ids),
        len(all_orphans),
    )

    async with async_session() as db:
        counts: dict[str, int] = {}
        block_ids_for_orphans: list[UUID] = []
        media_storage_keys: list[str] = []

        for eid in all_orphans:
            block_rows = (
                await db.execute(select(PrdBlock.id).where(PrdBlock.entity_id == eid))
            ).scalars().all()
            block_ids_for_orphans.extend(block_rows)

            media_rows = (
                await db.execute(
                    select(PrdMedia.storage_key).where(PrdMedia.entity_id == eid)
                )
            ).scalars().all()
            media_storage_keys.extend(media_rows)

        async def count(model, col) -> int:
            result = await db.execute(
                select(func.count())
                .select_from(model)
                .where(col.in_(all_orphans))
            )
            return result.scalar_one() or 0

        counts["prd_blocks"] = await count(PrdBlock, PrdBlock.entity_id)
        counts["prd_versions"] = await count(PrdVersion, PrdVersion.entity_id)
        counts["prd_comments"] = await count(PrdComment, PrdComment.entity_id)
        counts["prd_reviews"] = await count(PrdReview, PrdReview.entity_id)
        counts["prd_media"] = await count(PrdMedia, PrdMedia.entity_id)
        counts["prd_alignment_checks"] = await count(
            PrdAlignmentCheck, PrdAlignmentCheck.prd_entity_id
        )
        if block_ids_for_orphans:
            reactions_result = await db.execute(
                select(func.count())
                .select_from(PrdReaction)
                .where(PrdReaction.block_id.in_(block_ids_for_orphans))
            )
            counts["prd_reactions"] = reactions_result.scalar_one() or 0
        else:
            counts["prd_reactions"] = 0

    logger.info("org=%s counts=%s media_blobs=%d", org_id, counts, len(media_storage_keys))

    if not apply:
        for eid in sorted(all_orphans, key=str):
            logger.info("  DRY RUN would purge entity_id=%s", eid)
        return {
            "org_id": str(org_id),
            "orphaned_entity_ids": len(all_orphans),
            "counts": counts,
            "apply": False,
        }

    from sqlalchemy import delete as sa_delete

    async with async_session() as db:
        if block_ids_for_orphans:
            await db.execute(
                sa_delete(PrdReaction).where(
                    PrdReaction.block_id.in_(block_ids_for_orphans)
                )
            )
        await db.execute(
            sa_delete(PrdComment).where(PrdComment.entity_id.in_(all_orphans))
        )
        await db.execute(
            sa_delete(PrdBlock).where(PrdBlock.entity_id.in_(all_orphans))
        )
        await db.execute(
            sa_delete(PrdVersion).where(PrdVersion.entity_id.in_(all_orphans))
        )
        await db.execute(
            sa_delete(PrdReview).where(PrdReview.entity_id.in_(all_orphans))
        )
        await db.execute(
            sa_delete(PrdMedia).where(PrdMedia.entity_id.in_(all_orphans))
        )
        await db.execute(
            sa_delete(PrdAlignmentCheck).where(
                PrdAlignmentCheck.prd_entity_id.in_(all_orphans)
            )
        )

        for eid in all_orphans:
            await _prune_wiki_refs(db, org_id, eid)

        await db.commit()

    blobs_deleted = await _delete_s3_blobs(media_storage_keys)
    logger.info("org=%s deleted_s3_blobs=%d", org_id, blobs_deleted)

    await invalidate_wiki_cache(org_id)

    return {
        "org_id": str(org_id),
        "orphaned_entity_ids": len(all_orphans),
        "counts": counts,
        "s3_blobs_deleted": blobs_deleted,
        "apply": True,
    }


async def run(target_org_id: UUID | None, apply: bool) -> None:
    async with async_session() as session:
        if target_org_id is not None:
            org_ids = [target_org_id]
        else:
            result = await session.execute(select(Organization.id))
            org_ids = [row[0] for row in result.fetchall()]

    summaries = []
    for org_id in org_ids:
        try:
            summary = await purge_org(org_id, apply)
        except Exception:
            logger.exception("Failed to process org=%s", org_id)
            continue
        summaries.append(summary)

    logger.info("Done. orgs=%d apply=%s", len(summaries), apply)
    for s in summaries:
        logger.info("  %s", s)


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
