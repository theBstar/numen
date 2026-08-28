"""Score orchestration: full-org scoring, delta updates, and cache-aware reads."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import get_entities_via_edge, list_edges
from src.graph import get_entity as graph_get_entity
from src.inference.cache import cache_scores, get_cached_scores
from src.inference.urgency import compute_batch, compute_prd_urgency
from src.shared.models import OrgMember, UrgencyScoreCache
from src.shared.types import EdgeType, EntityType, RoleType, UrgencyScore

# Entity types that are scorable work items
_SCORABLE_TYPES = {EntityType.TASK, EntityType.COMMIT_PR, EntityType.INCIDENT, EntityType.DOCUMENT}


# ── Helpers ──────────────────────────────────────────────────────────────


async def _get_org_members(db: AsyncSession, org_id: UUID) -> list[OrgMember]:
    """Return all members of an org that have a linked person entity."""
    result = await db.execute(
        select(OrgMember).where(
            and_(
                OrgMember.org_id == org_id,
                OrgMember.person_entity_id.isnot(None),
            )
        )
    )
    return list(result.scalars().all())


async def _get_entities_for_person(
    db: AsyncSession,
    org_id: UUID,
    person_entity_id: UUID,
) -> list[UUID]:
    """Return entity IDs of scorable items owned by or assigned to a person.

    Looks for OWNS edges where the person is the source.
    """
    owned_entities = await get_entities_via_edge(
        db, person_entity_id, EdgeType.OWNS, direction="outgoing", org_id=org_id
    )
    return [e.id for e in owned_entities if e.type in _SCORABLE_TYPES]


async def _compute_scores_with_dispatch(
    db: AsyncSession,
    org_id: UUID,
    person_id: UUID,
    entity_ids: list[UUID],
) -> list[UrgencyScore]:
    """Score entities using type-appropriate scoring functions.

    Routes DOCUMENT entities to ``compute_prd_urgency`` and all other
    scorable types to the standard ``compute_batch`` pipeline.
    """
    prd_ids: list[UUID] = []
    other_ids: list[UUID] = []

    for eid in entity_ids:
        entity = await graph_get_entity(db, eid, org_id=org_id)
        if entity is not None and entity.type == EntityType.DOCUMENT:
            prd_ids.append(eid)
        else:
            other_ids.append(eid)

    scores: list[UrgencyScore] = []

    # Score non-PRD entities with standard batch scorer
    if other_ids:
        scores.extend(await compute_batch(db, org_id, person_id, other_ids))

    # Score PRD documents with PRD-specific scorer
    for prd_id in prd_ids:
        prd_score = await compute_prd_urgency(db, prd_id, person_id, org_id)
        scores.append(prd_score)

    return scores


async def _persist_scores(db: AsyncSession, scores: list[UrgencyScore]) -> None:
    """Upsert scores into the UrgencyScoreCache table."""
    if not scores:
        return

    datetime.now(timezone.utc)
    for s in scores:
        stmt = (
            pg_insert(UrgencyScoreCache)
            .values(
                org_id=s.org_id,
                person_id=s.person_id,
                entity_id=s.entity_id,
                score=s.score,
                score_components=s.components,
                goal_ids=s.goal_ids,
                provenance=s.provenance,
                computed_at=s.computed_at,
                valid_until=None,
            )
            .on_conflict_do_update(
                constraint="uq_score_person_entity",
                set_={
                    "score": s.score,
                    "score_components": s.components,
                    "goal_ids": s.goal_ids,
                    "provenance": s.provenance,
                    "computed_at": s.computed_at,
                    "valid_until": None,
                },
            )
        )
        await db.execute(stmt)

    await db.flush()


async def _get_people_for_entities(
    db: AsyncSession,
    org_id: UUID,
    entity_ids: list[UUID],
) -> dict[UUID, list[UUID]]:
    """Map person_entity_id -> list of entity_ids they own from the given set."""
    entity_id_set = set(entity_ids)
    mapping: dict[UUID, list[UUID]] = {}
    for eid in entity_ids:
        edges = await list_edges(
            db, entity_id=eid, edge_type=EdgeType.OWNS, direction="incoming", org_id=org_id
        )
        for edge in edges:
            if edge.org_id == org_id and edge.to_entity_id in entity_id_set:
                mapping.setdefault(edge.from_entity_id, []).append(edge.to_entity_id)
    return mapping


# ── Public API ───────────────────────────────────────────────────────────


async def score_org(
    db: AsyncSession,
    org_id: UUID,
) -> dict[UUID, list[UrgencyScore]]:
    """Full scoring pass for an entire org.

    For every org member with a linked person entity, compute urgency scores
    for all their owned scorable entities.  Persist to DB and Redis.
    Returns ``{person_id: [UrgencyScore, ...]}``.
    """
    members = await _get_org_members(db, org_id)
    result: dict[UUID, list[UrgencyScore]] = {}

    for member in members:
        person_id = member.person_entity_id
        entity_ids = await _get_entities_for_person(db, org_id, person_id)
        if not entity_ids:
            result[person_id] = []
            continue

        scores = await _compute_scores_with_dispatch(db, org_id, person_id, entity_ids)
        await _persist_scores(db, scores)
        await cache_scores(scores)
        result[person_id] = scores

    await db.commit()
    return result


async def score_delta(
    db: AsyncSession,
    org_id: UUID,
    changed_entity_ids: list[UUID],
) -> dict[UUID, list[UrgencyScore]]:
    """Re-score only the changed entities and their connected people.

    More efficient than ``score_org`` for webhook-triggered updates.
    """
    if not changed_entity_ids:
        return {}

    person_to_entities = await _get_people_for_entities(db, org_id, changed_entity_ids)
    result: dict[UUID, list[UrgencyScore]] = {}

    for person_id, entity_ids in person_to_entities.items():
        scores = await _compute_scores_with_dispatch(db, org_id, person_id, entity_ids)
        await _persist_scores(db, scores)
        await cache_scores(scores)
        result[person_id] = scores

    await db.commit()
    return result


async def get_top_urgent(
    db: AsyncSession,
    org_id: UUID,
    person_id: UUID,
    role: RoleType,
    limit: int = 10,
) -> list[UrgencyScore]:
    """Get top N urgent items for a person.

    Tries Redis cache first; falls back to the DB ``urgency_scores`` table.
    """
    # Attempt Redis first
    cached = await get_cached_scores(org_id, person_id, limit=limit)
    if cached:
        entity_ids = [eid for eid, _ in cached]
        result = await db.execute(
            select(UrgencyScoreCache).where(
                and_(
                    UrgencyScoreCache.org_id == org_id,
                    UrgencyScoreCache.person_id == person_id,
                    UrgencyScoreCache.entity_id.in_(entity_ids),
                )
            )
        )
        rows = result.scalars().all()

        # Preserve Redis ordering
        row_map = {row.entity_id: row for row in rows}
        scores: list[UrgencyScore] = []
        for eid, cached_score in cached:
            row = row_map.get(eid)
            if row:
                scores.append(
                    UrgencyScore(
                        entity_id=row.entity_id,
                        person_id=row.person_id,
                        org_id=row.org_id,
                        score=row.score,
                        components=row.score_components,
                        goal_ids=row.goal_ids or [],
                        provenance=row.provenance or [],
                        computed_at=row.computed_at,
                    )
                )
        return scores[:limit]

    # Fallback: DB query ordered by score descending
    result = await db.execute(
        select(UrgencyScoreCache)
        .where(
            and_(
                UrgencyScoreCache.org_id == org_id,
                UrgencyScoreCache.person_id == person_id,
            )
        )
        .order_by(UrgencyScoreCache.score.desc())
        .limit(limit)
    )
    rows = result.scalars().all()

    return [
        UrgencyScore(
            entity_id=row.entity_id,
            person_id=row.person_id,
            org_id=row.org_id,
            score=row.score,
            components=row.score_components,
            goal_ids=row.goal_ids or [],
            provenance=row.provenance or [],
            computed_at=row.computed_at,
        )
        for row in rows
    ]
