"""Living pull-request + merge tracking endpoints.

The Mac app's Ship tab and the Numen MCP `update_pr_state` / `get_pr_state`
tools both go through this surface. All business logic lives in
`src/services/pr_lifecycle.py` so the two callers can never drift; this
module is just a thin REST adapter.

Endpoints (all under /api/living/tasks/{task_id}/):
  POST   /branch-pushed       telemetry: branch was just pushed up
  POST   /pull-request        upsert: a PR (or local merge intent) exists
  PATCH  /pull-request        partial update from a poll cycle
  POST   /merge               record the merge happened (PR or local)
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.services import pr_lifecycle as svc
from src.shared.models import LivingPullRequest
from src.shared.types import (
    LivingMergeStateStatus,
    LivingMergeStrategy,
    LivingPrProvider,
    LivingPrState,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/living/tasks", tags=["living"])


# ── Schemas ──────────────────────────────────────────────────────────


class BranchPushedIn(BaseModel):
    branch_name: str = Field(..., min_length=1, max_length=512)
    commit_sha: str = Field(..., min_length=4, max_length=64)


class PullRequestUpsertIn(BaseModel):
    branch_name: str = Field(..., min_length=1, max_length=512)
    base_branch: str = Field(..., min_length=1, max_length=512)
    provider: LivingPrProvider
    pr_number: int | None = None
    pr_url: str | None = None
    commit_head_sha: str | None = None
    draft: bool = False


class PullRequestPatchIn(BaseModel):
    pr_state: LivingPrState | None = None
    merge_state_status: LivingMergeStateStatus | None = None
    commit_head_sha: str | None = None


class MergeRecordIn(BaseModel):
    merge_strategy: LivingMergeStrategy
    merged_commit_sha: str = Field(..., min_length=4, max_length=64)


class PullRequestOut(BaseModel):
    id: UUID
    task_id: UUID
    org_id: UUID
    branch_name: str
    base_branch: str
    commit_head_sha: str | None
    provider: LivingPrProvider
    pr_number: int | None
    pr_url: str | None
    pr_state: LivingPrState
    merge_state_status: LivingMergeStateStatus
    merge_strategy: LivingMergeStrategy | None
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None


def _to_out(pr: LivingPullRequest) -> PullRequestOut:
    return PullRequestOut(
        id=pr.id,
        task_id=pr.task_id,
        org_id=pr.org_id,
        branch_name=pr.branch_name,
        base_branch=pr.base_branch,
        commit_head_sha=pr.commit_head_sha,
        provider=pr.provider,
        pr_number=pr.pr_number,
        pr_url=pr.pr_url,
        pr_state=pr.pr_state,
        merge_state_status=pr.merge_state_status,
        merge_strategy=pr.merge_strategy,
        created_at=pr.created_at,
        updated_at=pr.updated_at,
        merged_at=pr.merged_at,
    )


def _raise_http(e: svc.PrServiceError) -> None:
    raise HTTPException(status_code=e.http_status, detail=e.message)


# ── Routes (thin REST adapters; logic lives in src/services/pr_lifecycle.py) ──


@router.post("/{task_id}/branch-pushed", status_code=204)
async def record_branch_pushed(
    task_id: UUID,
    body: BranchPushedIn,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await svc.record_branch_pushed(
            db,
            principal.org_id,
            task_id,
            svc.BranchPushedInput(
                branch_name=body.branch_name, commit_sha=body.commit_sha
            ),
        )
    except svc.PrServiceError as e:
        _raise_http(e)
    return Response(status_code=204)


@router.post("/{task_id}/pull-request", response_model=PullRequestOut)
async def upsert_pull_request(
    task_id: UUID,
    body: PullRequestUpsertIn,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> PullRequestOut:
    try:
        pr = await svc.upsert_pull_request(
            db,
            principal.org_id,
            task_id,
            svc.PullRequestUpsertInput(
                branch_name=body.branch_name,
                base_branch=body.base_branch,
                provider=body.provider,
                pr_number=body.pr_number,
                pr_url=body.pr_url,
                commit_head_sha=body.commit_head_sha,
                draft=body.draft,
            ),
        )
    except svc.PrServiceError as e:
        _raise_http(e)
    return _to_out(pr)


@router.patch("/{task_id}/pull-request", response_model=PullRequestOut)
async def patch_pull_request(
    task_id: UUID,
    body: PullRequestPatchIn,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> PullRequestOut:
    try:
        pr = await svc.patch_pull_request(
            db,
            principal.org_id,
            task_id,
            svc.PullRequestPatchInput(
                pr_state=body.pr_state,
                merge_state_status=body.merge_state_status,
                commit_head_sha=body.commit_head_sha,
            ),
        )
    except svc.PrServiceError as e:
        _raise_http(e)
    return _to_out(pr)


@router.post("/{task_id}/merge", response_model=PullRequestOut)
async def record_merge(
    task_id: UUID,
    body: MergeRecordIn,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> PullRequestOut:
    try:
        pr = await svc.record_merge(
            db,
            principal.org_id,
            task_id,
            svc.MergeRecordInput(
                merge_strategy=body.merge_strategy,
                merged_commit_sha=body.merged_commit_sha,
            ),
        )
    except svc.PrServiceError as e:
        _raise_http(e)
    return _to_out(pr)
