"""PRD-proposal service (WS1).

Race-safe propose -> approve flow:
  - Propose: stores SHA256 hash of WikiFeature.content as base_content_hash.
  - Approve: re-fetches the feature, recomputes hash. If it drifted (regen
    or another approval landed), transitions proposal to 'stale' and
    raises ProposalStale; the agent must re-propose with a fresh diff.
  - Concurrent propose attempts: at most one PENDING per (org, slug,
    anchor) via a partial unique index. Second propose returns
    DuplicatePending.

Per T1 (autoplan locked): no wiki_feature_revisions table; the wiki
content is mutated in place. Hash-stale rejection is the only race
guard; safe for current scale.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import PRDProposal, WikiFeature

logger = logging.getLogger(__name__)


DEFAULT_EXPIRY_DAYS = 7


class ProposalErrorCode:
    FEATURE_NOT_FOUND = "feature_slug_not_found"
    DUPLICATE_PENDING = "proposal_duplicate_pending"
    NOT_FOUND = "proposal_not_found"
    NOT_PENDING = "proposal_not_pending"
    STALE = "proposal_stale"


class ProposalServiceError(Exception):
    def __init__(self, code: str, message: str, *, extra: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.extra = extra or {}


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass
class ProposeIn:
    feature_slug: str
    section_anchor: str
    diff_md: str
    rationale: str = ""
    expires_in_days: int = DEFAULT_EXPIRY_DAYS


async def propose_prd_update(
    db: AsyncSession,
    org_id: UUID,
    proposer_user_id: UUID | None,
    payload: ProposeIn,
) -> PRDProposal:
    """Create a pending proposal. Snapshots the current wiki content hash.

    Raises:
      ProposalServiceError(FEATURE_NOT_FOUND) if the slug doesn't exist
        in this org.
      ProposalServiceError(DUPLICATE_PENDING) if a pending proposal
        already exists for the same (org, slug, anchor).
    """
    feature = (
        await db.execute(
            select(WikiFeature).where(
                WikiFeature.org_id == org_id,
                WikiFeature.slug == payload.feature_slug,
            )
        )
    ).scalar_one_or_none()
    if feature is None:
        raise ProposalServiceError(
            ProposalErrorCode.FEATURE_NOT_FOUND,
            f"No wiki feature with slug {payload.feature_slug!r} in this org.",
        )

    base_hash = _hash_content(feature.content or "")
    expires_at = datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)

    proposal = PRDProposal(
        org_id=org_id,
        proposer_user_id=proposer_user_id,
        feature_slug=payload.feature_slug,
        section_anchor=payload.section_anchor,
        diff_md=payload.diff_md,
        rationale=payload.rationale,
        base_content_hash=base_hash,
        base_updated_at=feature.updated_at,
        status="pending",
        expires_at=expires_at,
    )
    db.add(proposal)
    try:
        await db.flush()
    except IntegrityError as e:
        await db.rollback()
        # The partial unique index trips when another pending proposal
        # already targets this (org, slug, anchor).
        raise ProposalServiceError(
            ProposalErrorCode.DUPLICATE_PENDING,
            (
                f"A pending proposal already exists for "
                f"{payload.feature_slug}#{payload.section_anchor}. "
                "Wait for it to be decided or use list_proposals to find it."
            ),
        ) from e

    await db.commit()
    return proposal


async def get_proposal(
    db: AsyncSession,
    org_id: UUID,
    proposal_id: UUID,
) -> PRDProposal:
    """Cross-org safe fetch by id. Raises NOT_FOUND if not in this org."""
    proposal = (
        await db.execute(
            select(PRDProposal).where(
                PRDProposal.id == proposal_id,
                PRDProposal.org_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if proposal is None:
        raise ProposalServiceError(
            ProposalErrorCode.NOT_FOUND,
            f"No proposal {proposal_id} in this org.",
        )
    return proposal


async def list_proposals(
    db: AsyncSession,
    org_id: UUID,
    *,
    status: str | None = None,
    feature_slug: str | None = None,
    proposer_user_id: UUID | None = None,
    limit: int = 50,
) -> list[PRDProposal]:
    """List proposals scoped to org, optionally filtered."""
    stmt = select(PRDProposal).where(PRDProposal.org_id == org_id)
    if status is not None:
        stmt = stmt.where(PRDProposal.status == status)
    if feature_slug is not None:
        stmt = stmt.where(PRDProposal.feature_slug == feature_slug)
    if proposer_user_id is not None:
        stmt = stmt.where(PRDProposal.proposer_user_id == proposer_user_id)
    stmt = stmt.order_by(PRDProposal.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def approve_proposal(
    db: AsyncSession,
    org_id: UUID,
    proposal_id: UUID,
    decider_user_id: UUID,
    *,
    apply_diff_as_full_replacement: bool = True,
) -> PRDProposal:
    """Approve a pending proposal. Hash-stale check inside.

    apply_diff_as_full_replacement (default True): treats diff_md as the new
    full content for the section. False would require a real markdown-diff
    apply; deferred until WS1+1.

    Raises:
      ProposalServiceError(NOT_FOUND) if not in this org.
      ProposalServiceError(NOT_PENDING) if status != 'pending'.
      ProposalServiceError(STALE) if WikiFeature.content hash drifted.
    """
    proposal = await get_proposal(db, org_id, proposal_id)
    if proposal.status != "pending":
        raise ProposalServiceError(
            ProposalErrorCode.NOT_PENDING,
            f"Proposal {proposal_id} is {proposal.status}, not pending.",
        )

    feature = (
        await db.execute(
            select(WikiFeature).where(
                WikiFeature.org_id == org_id,
                WikiFeature.slug == proposal.feature_slug,
            )
        )
    ).scalar_one_or_none()
    if feature is None:
        raise ProposalServiceError(
            ProposalErrorCode.FEATURE_NOT_FOUND,
            f"Wiki feature {proposal.feature_slug!r} no longer exists.",
        )

    current_hash = _hash_content(feature.content or "")
    if current_hash != proposal.base_content_hash:
        proposal.status = "stale"
        proposal.decided_at = datetime.now(timezone.utc)
        proposal.decided_reason = (
            "Content drifted between propose and approve. Re-propose."
        )
        await db.commit()
        raise ProposalServiceError(
            ProposalErrorCode.STALE,
            (
                f"Wiki feature {proposal.feature_slug!r} changed since this "
                "proposal was filed. The diff would apply against the wrong base. "
                "Re-call propose_prd_update with a fresh diff."
            ),
            extra={"current_base_hash": current_hash},
        )

    # Apply: replace the section with diff_md content. T1 decision = lossy
    # in-place mutation. Mark feature as manually edited so wiki regenerator
    # doesn't overwrite.
    if apply_diff_as_full_replacement:
        new_content = proposal.diff_md
    else:
        new_content = feature.content  # placeholder for future markdown-diff merge

    feature.content = new_content
    feature.summary = (new_content or "")[:500]
    feature.is_manual = True
    feature.updated_at = datetime.now(timezone.utc)

    proposal.status = "applied"
    proposal.decided_by_user_id = decider_user_id
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.applied_content_hash = _hash_content(new_content or "")

    await db.commit()
    return proposal


async def reject_proposal(
    db: AsyncSession,
    org_id: UUID,
    proposal_id: UUID,
    decider_user_id: UUID,
    *,
    reason: str | None = None,
) -> PRDProposal:
    """Reject a pending proposal. Idempotent on already-rejected."""
    proposal = await get_proposal(db, org_id, proposal_id)
    if proposal.status not in ("pending", "rejected"):
        raise ProposalServiceError(
            ProposalErrorCode.NOT_PENDING,
            f"Proposal {proposal_id} is {proposal.status}, cannot reject.",
        )
    if proposal.status == "rejected":
        return proposal
    proposal.status = "rejected"
    proposal.decided_by_user_id = decider_user_id
    proposal.decided_at = datetime.now(timezone.utc)
    proposal.decided_reason = reason
    await db.commit()
    return proposal


async def expire_stale_proposals(db: AsyncSession) -> int:
    """Worker entrypoint: transition pending proposals past expires_at to 'expired'.

    Returns count expired. Idempotent.
    """
    now = datetime.now(timezone.utc)
    rows = (
        await db.execute(
            select(PRDProposal).where(
                PRDProposal.status == "pending",
                PRDProposal.expires_at < now,
            )
        )
    ).scalars().all()
    for r in rows:
        r.status = "expired"
        r.decided_at = now
        r.decided_reason = "Auto-expired (no decision before deadline)."
    if rows:
        await db.commit()
    return len(rows)
