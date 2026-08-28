"""Review workflow and lifecycle management for PRD documents.

Handles reviewer/stakeholder management via FalkorDB edges, review
submission and tracking via PostgreSQL PrdReview records, and status
transition validation with review-gate enforcement.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_repository import (
    get_edge_by_triple,
    get_entities_via_edge,
    upsert_edge,
)
from src.shared.models import OrgMember, PrdReview, PrdVersion
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityType,
    PrdReviewStatus,
    PrdStatus,
)

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────


async def _get_member_person_entity_id(db: AsyncSession, member_id: UUID) -> UUID:
    """Look up the person_entity_id for an OrgMember, raising 404 if missing."""
    result = await db.execute(select(OrgMember.person_entity_id).where(OrgMember.id == member_id))
    person_entity_id = result.scalar_one_or_none()
    if person_entity_id is None:
        raise HTTPException(
            status_code=400,
            detail="Member does not have a linked person entity",
        )
    return person_entity_id


async def _get_member_display_name(db: AsyncSession, member_id: UUID) -> str | None:
    """Look up display name for an org member."""
    result = await db.execute(select(OrgMember.display_name).where(OrgMember.id == member_id))
    return result.scalar_one_or_none()


async def _get_latest_version(db: AsyncSession, entity_id: UUID) -> int:
    """Get the latest version number for a PRD entity."""
    result = await db.execute(
        select(func.max(PrdVersion.version)).where(PrdVersion.entity_id == entity_id)
    )
    return result.scalar_one() or 0


async def _delete_edge_by_triple(
    db: AsyncSession,
    org_id: UUID,
    from_entity_id: UUID,
    to_entity_id: UUID,
    edge_type: EdgeType,
) -> None:
    """Delete a specific edge by its (from, to, type) triple."""
    from src.graph.falkor_repository import delete_edge_by_id

    edge = await get_edge_by_triple(db, from_entity_id, to_entity_id, edge_type, org_id=org_id)
    if edge is not None:
        edge_id = edge.id
        if isinstance(edge_id, str):
            edge_id = UUID(edge_id)
        await delete_edge_by_id(db, edge_id, org_id=org_id)


# ── Reviewer management ─────────────────────────────────────────────


async def add_reviewer(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    reviewer_member_id: UUID,
) -> dict:
    """Add a reviewer by creating a REVIEWER_OF edge and PrdReview record.

    The edge goes from the reviewer's Person entity to the PRD Document entity.
    A PrdReview record is created with status=pending for the current version.
    """
    person_entity_id = await _get_member_person_entity_id(db, reviewer_member_id)
    reviewer_name = await _get_member_display_name(db, reviewer_member_id)

    # Create REVIEWER_OF edge: Person -> Document
    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=person_entity_id,
            to_entity_id=entity_id,
            type=EdgeType.REVIEWER_OF,
            weight=1.0,
            confidence=1.0,
            evidence=[{"source": "prd_review", "added_by": str(member_id)}],
        ),
    )

    # Create PrdReview record with pending status
    version = await _get_latest_version(db, entity_id)
    if version == 0:
        version = 1

    # Check if review already exists for this reviewer+entity+version
    existing = await db.execute(
        select(PrdReview).where(
            PrdReview.entity_id == entity_id,
            PrdReview.reviewer_id == reviewer_member_id,
            PrdReview.version == version,
        )
    )
    review = existing.scalar_one_or_none()

    if review is None:
        review = PrdReview(
            org_id=org_id,
            entity_id=entity_id,
            reviewer_id=reviewer_member_id,
            version=version,
            status=PrdReviewStatus.PENDING,
        )
        db.add(review)
        await db.flush()

    return {
        "person_id": person_entity_id,
        "person_name": reviewer_name or "Unknown",
        "role_type": "reviewer",
        "member_id": reviewer_member_id,
    }


async def remove_reviewer(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    reviewer_member_id: UUID,
) -> None:
    """Remove a reviewer by deleting the REVIEWER_OF edge."""
    person_entity_id = await _get_member_person_entity_id(db, reviewer_member_id)

    await _delete_edge_by_triple(db, org_id, person_entity_id, entity_id, EdgeType.REVIEWER_OF)


# ── Stakeholder management ──────────────────────────────────────────


async def add_stakeholder(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    stakeholder_member_id: UUID,
) -> dict:
    """Add a stakeholder by creating a STAKEHOLDER_OF edge.

    The edge goes from the stakeholder's Person entity to the PRD Document entity.
    """
    person_entity_id = await _get_member_person_entity_id(db, stakeholder_member_id)
    stakeholder_name = await _get_member_display_name(db, stakeholder_member_id)

    # Create STAKEHOLDER_OF edge: Person -> Document
    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=person_entity_id,
            to_entity_id=entity_id,
            type=EdgeType.STAKEHOLDER_OF,
            weight=1.0,
            confidence=1.0,
            evidence=[{"source": "prd_stakeholder", "added_by": str(member_id)}],
        ),
    )

    return {
        "person_id": person_entity_id,
        "person_name": stakeholder_name or "Unknown",
        "role_type": "stakeholder",
        "member_id": stakeholder_member_id,
    }


async def remove_stakeholder(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    stakeholder_member_id: UUID,
) -> None:
    """Remove a stakeholder by deleting the STAKEHOLDER_OF edge."""
    person_entity_id = await _get_member_person_entity_id(db, stakeholder_member_id)

    await _delete_edge_by_triple(db, org_id, person_entity_id, entity_id, EdgeType.STAKEHOLDER_OF)


# ── Review submission ───────────────────────────────────────────────


async def submit_review(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    reviewer_member_id: UUID,
    status: PrdReviewStatus,
    comment: str | None = None,
) -> PrdReview:
    """Submit a review decision (approve or request changes).

    Updates the PrdReview record for this reviewer on the current version.
    """
    version = await _get_latest_version(db, entity_id)
    if version == 0:
        version = 1

    # Find the existing review record
    result = await db.execute(
        select(PrdReview).where(
            PrdReview.entity_id == entity_id,
            PrdReview.reviewer_id == reviewer_member_id,
            PrdReview.version == version,
        )
    )
    review = result.scalar_one_or_none()

    if review is None:
        raise HTTPException(
            status_code=404,
            detail="No pending review found for this reviewer",
        )

    review.status = status
    review.comment = comment
    await db.flush()

    return review


# ── Review queries ──────────────────────────────────────────────────


async def list_reviews(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> list[PrdReview]:
    """List all reviews for a PRD, most recent first."""
    result = await db.execute(
        select(PrdReview)
        .where(
            PrdReview.org_id == org_id,
            PrdReview.entity_id == entity_id,
        )
        .order_by(PrdReview.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_review_summary(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> dict:
    """Get summary of review status for a PRD.

    Returns counts by status and whether all reviewers have approved.
    """
    version = await _get_latest_version(db, entity_id)
    if version == 0:
        version = 1

    result = await db.execute(
        select(PrdReview.status, func.count(PrdReview.id))
        .where(
            PrdReview.org_id == org_id,
            PrdReview.entity_id == entity_id,
            PrdReview.version == version,
        )
        .group_by(PrdReview.status)
    )

    counts: dict[str, int] = {}
    for row in result.all():
        status_val = row[0].value if hasattr(row[0], "value") else str(row[0])
        counts[status_val] = row[1]

    approved_count = counts.get(PrdReviewStatus.APPROVED.value, 0)
    changes_requested_count = counts.get(PrdReviewStatus.CHANGES_REQUESTED.value, 0)
    pending_count = counts.get(PrdReviewStatus.PENDING.value, 0)
    total_reviewers = approved_count + changes_requested_count + pending_count

    can_approve = total_reviewers > 0 and approved_count == total_reviewers

    return {
        "total_reviewers": total_reviewers,
        "approved_count": approved_count,
        "changes_requested_count": changes_requested_count,
        "pending_count": pending_count,
        "can_approve": can_approve,
    }


# ── Stakeholder queries ────────────────────────────────────────────


async def list_stakeholders(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> list[dict]:
    """List all stakeholders and reviewers for a PRD.

    Combines STAKEHOLDER_OF and REVIEWER_OF incoming edges, plus the OWNS edge
    for the owner. Returns person details with role classification.
    """
    stakeholders: list[dict] = []
    seen_person_ids: set[str] = set()

    # Owner via OWNS edge (incoming to the PRD)
    owner_people = await get_entities_via_edge(
        db,
        entity_id,
        EdgeType.OWNS,
        direction="incoming",
        target_type=EntityType.PERSON,
        org_id=org_id,
    )
    for person in owner_people:
        pid = str(person.id)
        if pid not in seen_person_ids:
            seen_person_ids.add(pid)
            member = await _find_member_by_person_entity(db, org_id, UUID(pid))
            stakeholders.append(
                {
                    "person_id": UUID(pid),
                    "person_name": person.canonical_name,
                    "role_type": "owner",
                    "member_id": member.id if member else None,
                }
            )

    # Stakeholders via STAKEHOLDER_OF edge
    stakeholder_people = await get_entities_via_edge(
        db,
        entity_id,
        EdgeType.STAKEHOLDER_OF,
        direction="incoming",
        target_type=EntityType.PERSON,
        org_id=org_id,
    )
    for person in stakeholder_people:
        pid = str(person.id)
        if pid not in seen_person_ids:
            seen_person_ids.add(pid)
            member = await _find_member_by_person_entity(db, org_id, UUID(pid))
            stakeholders.append(
                {
                    "person_id": UUID(pid),
                    "person_name": person.canonical_name,
                    "role_type": "stakeholder",
                    "member_id": member.id if member else None,
                }
            )

    # Reviewers via REVIEWER_OF edge
    reviewer_people = await get_entities_via_edge(
        db,
        entity_id,
        EdgeType.REVIEWER_OF,
        direction="incoming",
        target_type=EntityType.PERSON,
        org_id=org_id,
    )
    for person in reviewer_people:
        pid = str(person.id)
        if pid not in seen_person_ids:
            seen_person_ids.add(pid)
            member = await _find_member_by_person_entity(db, org_id, UUID(pid))
            stakeholders.append(
                {
                    "person_id": UUID(pid),
                    "person_name": person.canonical_name,
                    "role_type": "reviewer",
                    "member_id": member.id if member else None,
                }
            )

    return stakeholders


async def _find_member_by_person_entity(
    db: AsyncSession, org_id: UUID, person_entity_id: UUID
) -> OrgMember | None:
    """Find an OrgMember by their person_entity_id."""
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.person_entity_id == person_entity_id,
        )
    )
    return result.scalar_one_or_none()


# ── Status transition validation ────────────────────────────────────


# Allowed transitions: mapping from current_status -> set of valid next statuses.
# "any -> archived" is handled specially.
_ALLOWED_TRANSITIONS: dict[PrdStatus, set[PrdStatus]] = {
    PrdStatus.IDEA: {PrdStatus.DRAFT},
    PrdStatus.DRAFT: {PrdStatus.IN_REVIEW},
    PrdStatus.IN_REVIEW: {PrdStatus.APPROVED, PrdStatus.NEEDS_REVISION},
    PrdStatus.NEEDS_REVISION: {PrdStatus.DRAFT},
    PrdStatus.APPROVED: {PrdStatus.IN_PROGRESS},
    PrdStatus.IN_PROGRESS: {PrdStatus.SHIPPED},
    PrdStatus.SHIPPED: {PrdStatus.DEPRECATED},
    PrdStatus.DEPRECATED: set(),
    PrdStatus.ARCHIVED: set(),
}


async def validate_transition(
    current_status: PrdStatus,
    new_status: PrdStatus,
    review_summary: dict | None = None,
) -> tuple[bool, str]:
    """Validate if a status transition is allowed.

    Rules:
    - idea -> draft: always allowed
    - draft -> in_review: requires at least 1 reviewer
    - in_review -> approved: all reviewers must approve (or override by owner)
    - in_review -> needs_revision: any reviewer requested changes
    - needs_revision -> draft: always allowed (author acknowledges)
    - approved -> in_progress: always allowed
    - in_progress -> shipped: always allowed
    - shipped -> deprecated: always allowed
    - any -> archived: always allowed

    Returns (is_valid, reason_if_invalid).
    """
    # Any status -> archived is always allowed
    if new_status == PrdStatus.ARCHIVED:
        return True, ""

    # Same status is a no-op
    if current_status == new_status:
        return False, "Already in this status"

    # Check if transition is in the allowed set
    allowed = _ALLOWED_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        return (
            False,
            f"Cannot transition from {current_status.value} to {new_status.value}",
        )

    # Additional validation based on review state
    summary = review_summary or {}

    if current_status == PrdStatus.DRAFT and new_status == PrdStatus.IN_REVIEW:
        total = summary.get("total_reviewers", 0)
        if total < 1:
            return False, "At least 1 reviewer is required before moving to review"

    if current_status == PrdStatus.IN_REVIEW and new_status == PrdStatus.APPROVED:
        if not summary.get("can_approve", False):
            pending = summary.get("pending_count", 0)
            changes = summary.get("changes_requested_count", 0)
            if changes > 0:
                return (
                    False,
                    f"{changes} reviewer(s) requested changes - cannot approve",
                )
            if pending > 0:
                return (
                    False,
                    f"{pending} review(s) still pending - all must approve",
                )
            return False, "No reviewers have approved yet"

    return True, ""
