"""REST endpoints for PRD proposal review (WS1).

The frontend PrdProposalView.tsx hits these to render + decide proposals.
Mirrors the MCP surface for parity but uses HTTP for the human-facing
approval flow.

Endpoints (all under /api/prd/proposals):
  GET    /                         List proposals (auth user's org)
  GET    /{id}                     Fetch one
  POST   /{id}/approve             Approve (must be pending; hash-stale guard)
  POST   /{id}/reject              Reject with optional reason
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.services import proposals as svc
from src.shared.models import OrgMember, PRDProposal

router = APIRouter(prefix="/api/prd/proposals", tags=["prd"])


class ProposalOut(BaseModel):
    id: UUID
    org_id: UUID
    feature_slug: str
    section_anchor: str
    diff_md: str
    rationale: str
    status: str
    base_content_hash: str
    base_updated_at: datetime | None = None
    proposer_user_id: UUID | None = None
    decided_by_user_id: UUID | None = None
    decided_at: datetime | None = None
    decided_reason: str | None = None
    applied_content_hash: str | None = None
    created_at: datetime
    expires_at: datetime


class ProposalListOut(BaseModel):
    items: list[ProposalOut]
    count: int


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


def _to_out(p: PRDProposal) -> ProposalOut:
    return ProposalOut(
        id=p.id,
        org_id=p.org_id,
        feature_slug=p.feature_slug,
        section_anchor=p.section_anchor,
        diff_md=p.diff_md,
        rationale=p.rationale,
        status=p.status,
        base_content_hash=p.base_content_hash,
        base_updated_at=p.base_updated_at,
        proposer_user_id=p.proposer_user_id,
        decided_by_user_id=p.decided_by_user_id,
        decided_at=p.decided_at,
        decided_reason=p.decided_reason,
        applied_content_hash=p.applied_content_hash,
        created_at=p.created_at,
        expires_at=p.expires_at,
    )


def _http_for_svc_error(e: svc.ProposalServiceError) -> HTTPException:
    code_to_status = {
        svc.ProposalErrorCode.FEATURE_NOT_FOUND: 404,
        svc.ProposalErrorCode.NOT_FOUND: 404,
        svc.ProposalErrorCode.NOT_PENDING: 409,
        svc.ProposalErrorCode.STALE: 409,
        svc.ProposalErrorCode.DUPLICATE_PENDING: 409,
    }
    status = code_to_status.get(e.code, 500)
    return HTTPException(status_code=status, detail={"code": e.code, "message": e.message, **e.extra})


@router.get("", response_model=ProposalListOut)
async def list_proposals(
    status: str | None = Query(default=None),
    feature_slug: str | None = Query(default=None),
    only_mine: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
) -> ProposalListOut:
    proposals = await svc.list_proposals(
        db,
        member.org_id,
        status=status,
        feature_slug=feature_slug,
        proposer_user_id=member.user_id if only_mine else None,
        limit=limit,
    )
    return ProposalListOut(items=[_to_out(p) for p in proposals], count=len(proposals))


@router.get("/{proposal_id}", response_model=ProposalOut)
async def get_proposal(
    proposal_id: UUID,
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
) -> ProposalOut:
    try:
        proposal = await svc.get_proposal(db, member.org_id, proposal_id)
    except svc.ProposalServiceError as e:
        raise _http_for_svc_error(e) from e
    return _to_out(proposal)


@router.post("/{proposal_id}/approve", response_model=ProposalOut)
async def approve_proposal(
    proposal_id: UUID,
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
) -> ProposalOut:
    try:
        proposal = await svc.approve_proposal(db, member.org_id, proposal_id, member.user_id)
    except svc.ProposalServiceError as e:
        raise _http_for_svc_error(e) from e
    return _to_out(proposal)


@router.post("/{proposal_id}/reject", response_model=ProposalOut)
async def reject_proposal(
    proposal_id: UUID,
    body: RejectIn = RejectIn(),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
) -> ProposalOut:
    try:
        proposal = await svc.reject_proposal(
            db, member.org_id, proposal_id, member.user_id, reason=body.reason
        )
    except svc.ProposalServiceError as e:
        raise _http_for_svc_error(e) from e
    return _to_out(proposal)
