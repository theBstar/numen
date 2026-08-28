"""Cascade-archive for PRDs.

`delete_prd` is a soft delete: the FalkorDB Entity node survives with
prd_status="ARCHIVED" so an un-archive restores a fully usable PRD. Content
(PrdBlock / PrdVersion / PrdComment / PrdReaction / PrdReview / PrdMedia and
S3 blobs) is preserved for the same reason.

What this module cleans up on archive — the non-restorable derived artifacts:

- JSONB references in WikiFeature / WikiConcept / WikiProductSummary so the
  wiki stops synthesising content from the archived PRD. Rows whose last
  reference was the archived PRD are deleted.
- FalkorDB edges touching the entity in either direction. Connected entities
  (tasks, goals, people) survive.
- Redis wiki cache key (so the next read regenerates).

Side effects queued, not awaited inline:
- A fresh LLM-based wiki regeneration is scheduled via asyncio.create_task so
  the DELETE endpoint returns promptly. The synchronous JSONB prune already
  makes the wiki correct for features whose last source was removed; regen
  refreshes prose for features that still have other sources.

Folders cascade: children are archived depth-first before the folder itself.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_repository import (
    delete_edges_for_entity,
    get_edges,
    get_entity,
    update_entity,
)
from src.prd.wiki import invalidate_wiki_cache
from src.shared.database import async_session
from src.shared.models import (
    AuditLog,
    PrdBlock,
    WikiConcept,
    WikiFeature,
    WikiProductSummary,
)
from src.shared.types import EdgeType, PrdStatus

logger = logging.getLogger(__name__)


async def cascade_archive_prd(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> None:
    """Archive a PRD and clean up its derived artifacts.

    Folders cascade to children depth-first. The Entity node and its content
    (blocks / versions / media) are preserved; only derived refs are pruned.
    """
    from fastapi import HTTPException

    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="PRD not found")

    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    child_ids = await _get_children(db, org_id, entity_id)
    for child_id in child_ids:
        await cascade_archive_prd(db, org_id, child_id)

    block_count = await _count_blocks(db, entity_id)
    title = props.get("canonical_name") or (
        entity.canonical_name if hasattr(entity, "canonical_name") else None
    )

    db.add(
        AuditLog(
            org_id=org_id,
            action="prd.archived",
            resource_type="prd",
            resource_id=entity_id,
            details={
                "entity_id": str(entity_id),
                "title": title,
                "child_count": len(child_ids),
                "block_count": block_count,
                "previous_status": props.get("prd_status"),
            },
        )
    )

    await _prune_wiki_refs(db, org_id, entity_id)

    archived_props = dict(props)
    archived_props["prd_status"] = PrdStatus.ARCHIVED.value
    await update_entity(
        db,
        entity_id,
        org_id=org_id,
        properties=archived_props,
        merge_properties=False,
    )

    try:
        deleted = await delete_edges_for_entity(db, entity_id, org_id=org_id)
        logger.info(
            "cascade_archive_prd org=%s entity=%s deleted_edges=%d", org_id, entity_id, deleted
        )
    except Exception:
        logger.exception(
            "cascade_archive_prd failed deleting edges org=%s entity=%s", org_id, entity_id
        )

    try:
        await invalidate_wiki_cache(org_id)
    except Exception:
        logger.exception("cascade_archive_prd failed invalidating cache org=%s", org_id)

    _schedule_wiki_regen(org_id)


async def _get_children(
    db: AsyncSession, org_id: UUID, entity_id: UUID
) -> list[UUID]:
    """Return entity_ids of PRDs contained by this folder (outgoing CONTAINS edges)."""
    edges = await get_edges(
        db,
        entity_id,
        edge_types=[EdgeType.CONTAINS],
        direction="outgoing",
        org_id=org_id,
    )
    result: list[UUID] = []
    for edge in edges:
        to_id = edge.to_entity_id
        if isinstance(to_id, str):
            try:
                result.append(UUID(to_id))
            except ValueError:
                continue
        elif isinstance(to_id, UUID):
            result.append(to_id)
    return result


async def _count_blocks(db: AsyncSession, entity_id: UUID) -> int:
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).select_from(PrdBlock).where(PrdBlock.entity_id == entity_id)
    )
    return result.scalar_one() or 0


async def _prune_wiki_refs(
    db: AsyncSession, org_id: UUID, entity_id: UUID
) -> None:
    """Remove the archived entity_id from every WikiFeature / WikiConcept /
    WikiProductSummary reference in this org.

    Rows whose last-known reference was the archived entity are deleted.
    """
    eid_str = str(entity_id)

    features = (
        await db.execute(select(WikiFeature).where(WikiFeature.org_id == org_id))
    ).scalars().all()
    for feature in features:
        source_ids = list(feature.source_entity_ids or [])
        filtered_sources = [s for s in source_ids if str(s) != eid_str]

        prd_refs = list(feature.prd_references or [])
        filtered_refs = [
            ref
            for ref in prd_refs
            if str(ref.get("entity_id") if isinstance(ref, dict) else ref) != eid_str
        ]

        if not filtered_sources and not filtered_refs:
            await db.execute(delete(WikiFeature).where(WikiFeature.id == feature.id))
            continue

        if filtered_sources != source_ids or filtered_refs != prd_refs:
            await db.execute(
                update(WikiFeature)
                .where(WikiFeature.id == feature.id)
                .values(
                    source_entity_ids=filtered_sources,
                    prd_references=filtered_refs,
                )
            )

    concepts = (
        await db.execute(select(WikiConcept).where(WikiConcept.org_id == org_id))
    ).scalars().all()
    for concept in concepts:
        prd_refs = list(concept.prd_references or [])
        filtered_refs = [
            ref
            for ref in prd_refs
            if str(ref.get("entity_id") if isinstance(ref, dict) else ref) != eid_str
        ]

        if not filtered_refs:
            await db.execute(delete(WikiConcept).where(WikiConcept.id == concept.id))
            continue

        if filtered_refs != prd_refs:
            await db.execute(
                update(WikiConcept)
                .where(WikiConcept.id == concept.id)
                .values(prd_references=filtered_refs)
            )

    summary = (
        await db.execute(
            select(WikiProductSummary).where(WikiProductSummary.org_id == org_id)
        )
    ).scalar_one_or_none()
    if summary is not None:
        hashes = dict(summary.prd_hashes or {})
        if eid_str in hashes:
            del hashes[eid_str]
            if not hashes:
                await db.execute(
                    delete(WikiProductSummary).where(WikiProductSummary.id == summary.id)
                )
            else:
                await db.execute(
                    update(WikiProductSummary)
                    .where(WikiProductSummary.id == summary.id)
                    .values(
                        prd_hashes=hashes,
                        prd_count=len(hashes),
                        source_hash=None,
                    )
                )


def _schedule_wiki_regen(org_id: UUID) -> None:
    """Fire-and-forget wiki regeneration in a fresh DB session.

    Best-effort: if the event loop dies mid-task the regen is lost, but the
    JSONB prune already left the wiki accurate for removed sources, and the
    next manual /wiki/generate or scheduled regen will catch up.
    """
    try:
        asyncio.create_task(_run_wiki_regen(org_id))
    except RuntimeError:
        logger.debug("no running event loop, skipping wiki regen for org=%s", org_id)


async def _run_wiki_regen(org_id: UUID) -> None:
    from src.prd.wiki_generator import generate_wiki

    try:
        async with async_session() as session:
            await generate_wiki(session, org_id)
            await session.commit()
        logger.info("background wiki regen completed for org=%s", org_id)
    except Exception:
        logger.exception("background wiki regen failed for org=%s", org_id)
