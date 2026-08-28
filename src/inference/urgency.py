"""Urgency scoring engine with hardcoded v1 weights."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import get_connected_entity_ids, get_entities_by_ids, get_entity
from src.shared.models import Edge, PrdAlignmentCheck, PrdComment, PrdReview
from src.shared.types import EdgeType, EntityType, PrdReviewStatus, UrgencyScore

# ── V1 weight constants ──────────────────────────────────────────────────

WEIGHTS: dict[str, float] = {
    "staleness_days": 0.25,
    "is_blocking_others": 0.35,
    "downstream_blocked_count": 0.15,
    "mention_count_24h": 0.10,
    "goal_criticality": 0.10,
    "is_in_current_sprint": 0.05,
}

_STALENESS_CAP_DAYS = 14
_MAX_TRANSITIVE_DEPTH = 10

# ── PRD-specific weight constants ───────────────────────────────────────

PRD_WEIGHTS: dict[str, float] = {
    "prd_staleness": 0.20,
    "prd_review_pending_days": 0.25,
    "prd_spec_gap_count": 0.30,
    "prd_unresolved_comments": 0.15,
    "prd_goal_criticality": 0.10,
}

_PRD_STALENESS_CAP_DAYS = 30
_PRD_REVIEW_PENDING_CAP_DAYS = 14
_PRD_SPEC_GAP_CAP = 5
_PRD_UNRESOLVED_COMMENTS_CAP = 10


# ── Internal factor helpers ──────────────────────────────────────────────


async def _staleness_factor(db: AsyncSession, entity_id: UUID, org_id: UUID) -> tuple[float, dict]:
    """Return normalised staleness (0-1) and provenance info."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        return 0.0, {"staleness_days": 0, "note": "entity not found"}
    updated_at = entity.updated_at

    now = datetime.now(timezone.utc)
    delta_days = (now - updated_at).total_seconds() / 86400
    capped = min(delta_days, _STALENESS_CAP_DAYS)
    normalised = capped / _STALENESS_CAP_DAYS
    return normalised, {
        "factor": "staleness_days",
        "staleness_days": round(delta_days, 2),
        "capped_at": _STALENESS_CAP_DAYS,
        "explanation": (
            f"Last updated {round(delta_days, 1)} days ago (capped at {_STALENESS_CAP_DAYS})"
        ),
        "evidence": [{"entity_id": str(entity_id), "updated_at": str(updated_at)}],
    }


async def _is_blocking_factor(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """1.0 if entity has outgoing BLOCKS edges, else 0.0."""
    blocked_ids = await get_connected_entity_ids(
        db, entity_id, EdgeType.BLOCKS, direction="outgoing", org_id=org_id
    )
    count = len(blocked_ids)
    is_blocking = 1.0 if count > 0 else 0.0
    return is_blocking, {
        "factor": "is_blocking_others",
        "blocked_count": count,
        "explanation": f"This item is blocking {count} other item(s)"
        if count > 0
        else "Not blocking any other items",
        "evidence": [{"blocked_entity_id": str(e_id)} for e_id in blocked_ids],
    }


async def _downstream_blocked_count(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """Count transitive BLOCKS chain length, normalised to 0-1 (cap at _MAX_TRANSITIVE_DEPTH)."""
    visited: set[UUID] = set()
    frontier: list[UUID] = [entity_id]
    depth = 0

    while frontier and depth < _MAX_TRANSITIVE_DEPTH:
        next_ids_all: list[UUID] = []
        for fid in frontier:
            connected = await get_connected_entity_ids(
                db, fid, EdgeType.BLOCKS, direction="outgoing", org_id=org_id
            )
            next_ids_all.extend(connected)
        next_ids = [eid for eid in next_ids_all if eid not in visited]
        if not next_ids:
            break
        visited.update(next_ids)
        frontier = next_ids
        depth += 1

    chain_len = len(visited)
    normalised = min(chain_len / _MAX_TRANSITIVE_DEPTH, 1.0)
    return normalised, {
        "factor": "downstream_blocked_count",
        "chain_length": depth,
        "transitive_blocked_count": chain_len,
        "explanation": f"Transitive blocking chain of depth {depth} ({chain_len} entities downstream)"
        if chain_len > 0
        else "No transitive blocking chain",
        "evidence": [{"chain": [str(eid) for eid in visited]}] if visited else [],
    }


async def _mention_count_24h(db: AsyncSession, entity_id: UUID) -> tuple[float, dict]:
    """Count MENTIONED_IN edges created in the last 24 hours, normalised (cap at 10)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.execute(
        select(func.count())
        .select_from(Edge)
        .where(
            and_(
                Edge.from_entity_id == entity_id,
                Edge.type == EdgeType.MENTIONED_IN,
                Edge.last_active_at >= cutoff,
            )
        )
    )
    count = result.scalar_one()
    normalised = min(count / 10.0, 1.0)
    return normalised, {
        "factor": "mention_count_24h",
        "mention_count": count,
        "window_hours": 24,
        "explanation": f"Mentioned {count} time(s) in the last 24 hours"
        if count > 0
        else "No mentions in the last 24 hours",
        "evidence": [{"entity_id": str(entity_id), "mention_count": count, "cutoff": str(cutoff)}],
    }


async def _goal_criticality(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, list[UUID], dict]:
    """Compute goal gap from TAGGED_TO edges pointing to Goal entities.

    Returns normalised criticality (0-1), list of goal IDs, and provenance.
    """
    goal_edge_target_ids = await get_connected_entity_ids(
        db, entity_id, EdgeType.TAGGED_TO, direction="outgoing", org_id=org_id
    )

    if not goal_edge_target_ids:
        return (
            0.0,
            [],
            {
                "factor": "goal_criticality",
                "goals_found": 0,
                "explanation": "No goals linked to this item",
                "evidence": [],
            },
        )

    # Fetch goal entities to inspect properties for current_value / target_value
    all_targets = await get_entities_by_ids(db, goal_edge_target_ids, org_id=org_id)
    goals = [g for g in all_targets if g.type == EntityType.GOAL]

    if not goals:
        return (
            0.0,
            [],
            {
                "factor": "goal_criticality",
                "goals_found": 0,
                "explanation": "No goal entities found for linked IDs",
                "evidence": [],
            },
        )

    goal_ids: list[UUID] = []
    max_gap = 0.0

    for goal in goals:
        goal_ids.append(goal.id)
        props = goal.properties or {}
        target = props.get("target_value")
        current = props.get("current_value")
        if target is not None and current is not None:
            try:
                target_f = float(target)
                current_f = float(current)
                if target_f > 0:
                    gap = max(0.0, (target_f - current_f) / target_f)
                    max_gap = max(max_gap, gap)
            except (ValueError, TypeError):
                pass

    normalised = min(max_gap, 1.0)
    return (
        normalised,
        goal_ids,
        {
            "factor": "goal_criticality",
            "goals_found": len(goals),
            "max_gap": round(max_gap, 4),
            "explanation": f"Linked to {len(goals)} goal(s) with max gap of {round(max_gap * 100, 1)}%"
            if max_gap > 0
            else f"Linked to {len(goals)} goal(s) - on track",
            "evidence": [{"goal_id": str(g.id), "goal_name": g.canonical_name} for g in goals],
        },
    )


async def _is_in_current_sprint(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """1.0 if entity properties indicate current sprint membership, else 0.0."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    props = entity.properties if entity else None
    if not props:
        return 0.0, {
            "factor": "is_in_current_sprint",
            "in_sprint": False,
            "explanation": "Entity not found or has no properties",
            "evidence": [],
        }

    in_sprint = bool(props.get("is_in_current_sprint", False))
    sprint_name = props.get("sprint_name", "current sprint") if in_sprint else None
    return (1.0 if in_sprint else 0.0), {
        "factor": "is_in_current_sprint",
        "in_sprint": in_sprint,
        "explanation": f"In {sprint_name}" if in_sprint else "Not in the current sprint",
        "evidence": [{"entity_id": str(entity_id), "sprint_name": sprint_name}]
        if in_sprint
        else [],
    }


# ── PRD-specific factor helpers ──────────────────────────────────────────


async def _prd_staleness_factor(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """Return normalised PRD staleness (0-1) and provenance info.

    Uses a 30-day cap instead of the general 14-day cap since PRDs
    evolve on a slower cadence than tasks.
    """
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        return 0.0, {"factor": "prd_staleness", "staleness_days": 0, "note": "entity not found"}
    updated_at = entity.updated_at

    now = datetime.now(timezone.utc)
    delta_days = (now - updated_at).total_seconds() / 86400
    capped = min(delta_days, _PRD_STALENESS_CAP_DAYS)
    normalised = capped / _PRD_STALENESS_CAP_DAYS
    return normalised, {
        "factor": "prd_staleness",
        "staleness_days": round(delta_days, 2),
        "capped_at": _PRD_STALENESS_CAP_DAYS,
        "explanation": (
            f"PRD last updated {round(delta_days, 1)} days ago"
            f" (capped at {_PRD_STALENESS_CAP_DAYS})"
        ),
        "evidence": [{"entity_id": str(entity_id), "updated_at": str(updated_at)}],
    }


async def _prd_review_pending_days(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """Return normalised pending review duration (0-1).

    Queries PrdReview for pending reviews and returns the max days any
    review has been pending, normalised to a 14-day cap.
    """
    result = await db.execute(
        select(PrdReview).where(
            and_(
                PrdReview.entity_id == entity_id,
                PrdReview.org_id == org_id,
                PrdReview.status == PrdReviewStatus.PENDING,
            )
        )
    )
    pending_reviews = list(result.scalars().all())
    if not pending_reviews:
        return 0.0, {
            "factor": "prd_review_pending_days",
            "max_pending_days": 0,
            "pending_count": 0,
            "explanation": "No pending reviews",
            "evidence": [],
        }

    now = datetime.now(timezone.utc)
    max_days = 0.0
    for review in pending_reviews:
        days = (now - review.created_at).total_seconds() / 86400
        max_days = max(max_days, days)

    normalised = min(max_days / _PRD_REVIEW_PENDING_CAP_DAYS, 1.0)
    return normalised, {
        "factor": "prd_review_pending_days",
        "max_pending_days": round(max_days, 2),
        "pending_count": len(pending_reviews),
        "capped_at": _PRD_REVIEW_PENDING_CAP_DAYS,
        "explanation": (
            f"{len(pending_reviews)} pending review(s), oldest waiting {round(max_days, 1)} days"
        ),
        "evidence": [
            {"review_id": str(r.id), "created_at": str(r.created_at)} for r in pending_reviews
        ],
    }


async def _prd_spec_gap_count(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """Return normalised spec gap count (0-1).

    Queries PrdAlignmentCheck for pending or acknowledged findings
    on this PRD, normalised to a cap of 5.
    """
    result = await db.execute(
        select(func.count())
        .select_from(PrdAlignmentCheck)
        .where(
            and_(
                PrdAlignmentCheck.prd_entity_id == entity_id,
                PrdAlignmentCheck.org_id == org_id,
                PrdAlignmentCheck.status.in_(["pending", "acknowledged"]),
            )
        )
    )
    count = result.scalar_one()
    normalised = min(count / _PRD_SPEC_GAP_CAP, 1.0)
    return normalised, {
        "factor": "prd_spec_gap_count",
        "gap_count": count,
        "capped_at": _PRD_SPEC_GAP_CAP,
        "explanation": f"{count} unresolved alignment finding(s)"
        if count > 0
        else "No spec gaps found",
        "evidence": [{"entity_id": str(entity_id), "pending_findings": count}],
    }


async def _prd_unresolved_comments(
    db: AsyncSession, entity_id: UUID, org_id: UUID
) -> tuple[float, dict]:
    """Return normalised unresolved comment count (0-1).

    Queries PrdComment for unresolved (is_resolved=False) comment threads
    on this PRD, normalised to a cap of 10.
    """
    result = await db.execute(
        select(func.count())
        .select_from(PrdComment)
        .where(
            and_(
                PrdComment.entity_id == entity_id,
                PrdComment.org_id == org_id,
                PrdComment.is_resolved == False,  # noqa: E712
                PrdComment.parent_id.is_(None),  # Only count root threads
            )
        )
    )
    count = result.scalar_one()
    normalised = min(count / _PRD_UNRESOLVED_COMMENTS_CAP, 1.0)
    return normalised, {
        "factor": "prd_unresolved_comments",
        "unresolved_count": count,
        "capped_at": _PRD_UNRESOLVED_COMMENTS_CAP,
        "explanation": f"{count} unresolved comment thread(s)"
        if count > 0
        else "All comment threads resolved",
        "evidence": [{"entity_id": str(entity_id), "unresolved_threads": count}],
    }


async def compute_prd_urgency(
    db: AsyncSession,
    entity_id: UUID,
    person_id: UUID,
    org_id: UUID,
) -> UrgencyScore:
    """Calculate composite urgency score for a PRD document entity.

    Uses PRD-specific factors and weights instead of the general task scoring.
    Factors:
    1. prd_staleness - days since last update, capped at 30
    2. prd_review_pending_days - max days any review has been pending, capped at 14
    3. prd_spec_gap_count - number of pending alignment findings, capped at 5
    4. prd_unresolved_comments - unresolved comment thread count, capped at 10
    5. prd_goal_criticality - max urgency of linked goals via TAGGED_TO
    """
    now = datetime.now(timezone.utc)

    staleness_val, staleness_prov = await _prd_staleness_factor(db, entity_id, org_id)
    review_val, review_prov = await _prd_review_pending_days(db, entity_id, org_id)
    gap_val, gap_prov = await _prd_spec_gap_count(db, entity_id, org_id)
    comments_val, comments_prov = await _prd_unresolved_comments(db, entity_id, org_id)
    goal_val, goal_ids, goal_prov = await _goal_criticality(db, entity_id, org_id)

    raw_score = (
        staleness_val * PRD_WEIGHTS["prd_staleness"]
        + review_val * PRD_WEIGHTS["prd_review_pending_days"]
        + gap_val * PRD_WEIGHTS["prd_spec_gap_count"]
        + comments_val * PRD_WEIGHTS["prd_unresolved_comments"]
        + goal_val * PRD_WEIGHTS["prd_goal_criticality"]
    )

    # Scale to 0-100
    score = round(raw_score * 100, 2)

    components = {
        "prd_staleness": {"value": round(staleness_val, 4), "weight": PRD_WEIGHTS["prd_staleness"]},
        "prd_review_pending_days": {
            "value": round(review_val, 4),
            "weight": PRD_WEIGHTS["prd_review_pending_days"],
        },
        "prd_spec_gap_count": {
            "value": round(gap_val, 4),
            "weight": PRD_WEIGHTS["prd_spec_gap_count"],
        },
        "prd_unresolved_comments": {
            "value": round(comments_val, 4),
            "weight": PRD_WEIGHTS["prd_unresolved_comments"],
        },
        "prd_goal_criticality": {
            "value": round(goal_val, 4),
            "weight": PRD_WEIGHTS["prd_goal_criticality"],
        },
    }

    factors = {
        "prd_staleness": (staleness_val, staleness_prov),
        "prd_review_pending_days": (review_val, review_prov),
        "prd_spec_gap_count": (gap_val, gap_prov),
        "prd_unresolved_comments": (comments_val, comments_prov),
        "prd_goal_criticality": (goal_val, goal_prov),
    }

    provenance = []
    for factor_name, (value, info) in factors.items():
        weight = PRD_WEIGHTS[factor_name]
        provenance.append(
            {
                "factor_name": factor_name,
                "weight": weight,
                "raw_value": round(value, 4),
                "weighted_value": round(value * weight * 100, 2),
                "explanation": info.get("explanation", ""),
                "evidence": info.get("evidence", []),
            }
        )

    return UrgencyScore(
        entity_id=entity_id,
        person_id=person_id,
        org_id=org_id,
        score=score,
        components=components,
        goal_ids=goal_ids,
        provenance=provenance,
        computed_at=now,
    )


# ── Public API ───────────────────────────────────────────────────────────


async def compute_urgency(
    db: AsyncSession,
    entity_id: UUID,
    person_id: UUID,
    org_id: UUID,
) -> UrgencyScore:
    """Calculate composite urgency score for a single entity for a specific person."""
    now = datetime.now(timezone.utc)

    staleness_val, staleness_prov = await _staleness_factor(db, entity_id, org_id)
    blocking_val, blocking_prov = await _is_blocking_factor(db, entity_id, org_id)
    downstream_val, downstream_prov = await _downstream_blocked_count(db, entity_id, org_id)
    mention_val, mention_prov = await _mention_count_24h(db, entity_id)
    goal_val, goal_ids, goal_prov = await _goal_criticality(db, entity_id, org_id)
    sprint_val, sprint_prov = await _is_in_current_sprint(db, entity_id, org_id)

    raw_score = (
        staleness_val * WEIGHTS["staleness_days"]
        + blocking_val * WEIGHTS["is_blocking_others"]
        + downstream_val * WEIGHTS["downstream_blocked_count"]
        + mention_val * WEIGHTS["mention_count_24h"]
        + goal_val * WEIGHTS["goal_criticality"]
        + sprint_val * WEIGHTS["is_in_current_sprint"]
    )

    # Scale to 0-100
    score = round(raw_score * 100, 2)

    components = {
        "staleness_days": {"value": round(staleness_val, 4), "weight": WEIGHTS["staleness_days"]},
        "is_blocking_others": {
            "value": round(blocking_val, 4),
            "weight": WEIGHTS["is_blocking_others"],
        },
        "downstream_blocked_count": {
            "value": round(downstream_val, 4),
            "weight": WEIGHTS["downstream_blocked_count"],
        },
        "mention_count_24h": {
            "value": round(mention_val, 4),
            "weight": WEIGHTS["mention_count_24h"],
        },
        "goal_criticality": {"value": round(goal_val, 4), "weight": WEIGHTS["goal_criticality"]},
        "is_in_current_sprint": {
            "value": round(sprint_val, 4),
            "weight": WEIGHTS["is_in_current_sprint"],
        },
    }

    # Build structured scoring traces for full provenance
    factors = {
        "staleness_days": (staleness_val, staleness_prov),
        "is_blocking_others": (blocking_val, blocking_prov),
        "downstream_blocked_count": (downstream_val, downstream_prov),
        "mention_count_24h": (mention_val, mention_prov),
        "goal_criticality": (goal_val, goal_prov),
        "is_in_current_sprint": (sprint_val, sprint_prov),
    }

    provenance = []
    for factor_name, (value, info) in factors.items():
        weight = WEIGHTS[factor_name]
        provenance.append(
            {
                "factor_name": factor_name,
                "weight": weight,
                "raw_value": round(value, 4),
                "weighted_value": round(value * weight * 100, 2),
                "explanation": info.get("explanation", ""),
                "evidence": info.get("evidence", []),
            }
        )

    return UrgencyScore(
        entity_id=entity_id,
        person_id=person_id,
        org_id=org_id,
        score=score,
        components=components,
        goal_ids=goal_ids,
        provenance=provenance,
        computed_at=now,
    )


async def compute_batch(
    db: AsyncSession,
    org_id: UUID,
    person_id: UUID,
    entity_ids: list[UUID],
) -> list[UrgencyScore]:
    """Compute urgency scores for multiple entities in batch."""
    scores: list[UrgencyScore] = []
    for eid in entity_ids:
        score = await compute_urgency(db, eid, person_id, org_id)
        scores.append(score)
    return scores
