"""PR lifecycle service - shared between REST handlers and MCP tools.

Centralizes the read/upsert/patch/merge mutations that previously lived
inline in src/api/living/pull_requests.py. Both the FastAPI routes and
the new MCP `update_pr_state` / `get_pr_state` tools call into here so
state-machine, event emission, and cross-org guards never drift.

Errors are raised as PrServiceError(code, message). Callers translate
to their own surface (HTTPException for REST; error_response envelope
for MCP).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.events import (
    BranchPushedEvent,
    MergeCompletedEvent,
    PrStateChangedEvent,
    bus,
)
from src.shared.models import LivingPullRequest, LivingTask
from src.shared.types import (
    LivingMergeStateStatus,
    LivingMergeStrategy,
    LivingPrProvider,
    LivingPrState,
    LivingTaskStatus,
)

logger = logging.getLogger(__name__)


class PrServiceErrorCode:
    TASK_NOT_FOUND = "task_not_found"
    PR_NOT_FOUND = "pr_not_found"
    INVALID_ENUM = "invalid_enum"


class PrServiceError(Exception):
    """Domain error raised by pr_lifecycle service functions."""

    def __init__(self, code: str, message: str, *, http_status: int = 404) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


# ── helpers ───────────────────────────────────────────────────────────


async def _load_task(db: AsyncSession, org_id: UUID, task_id: UUID) -> LivingTask:
    row = await db.execute(
        select(LivingTask).where(
            LivingTask.id == task_id, LivingTask.org_id == org_id
        )
    )
    task = row.scalar_one_or_none()
    if task is None:
        # Cross-org leak protection: pretend it doesn't exist.
        raise PrServiceError(
            PrServiceErrorCode.TASK_NOT_FOUND,
            "Task not found in this org.",
            http_status=404,
        )
    return task


async def _load_pr(db: AsyncSession, task_id: UUID) -> LivingPullRequest | None:
    row = await db.execute(
        select(LivingPullRequest).where(LivingPullRequest.task_id == task_id)
    )
    return row.scalar_one_or_none()


# ── public API ────────────────────────────────────────────────────────


@dataclass
class BranchPushedInput:
    branch_name: str
    commit_sha: str


async def record_branch_pushed(
    db: AsyncSession,
    org_id: UUID,
    task_id: UUID,
    payload: BranchPushedInput,
) -> None:
    """Telemetry event: a branch was just pushed for this task."""
    await _load_task(db, org_id, task_id)
    await bus.emit(
        BranchPushedEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            branch_name=payload.branch_name,
            commit_sha=payload.commit_sha,
        )
    )
    await db.commit()


@dataclass
class PullRequestUpsertInput:
    branch_name: str
    base_branch: str
    provider: LivingPrProvider
    pr_number: int | None = None
    pr_url: str | None = None
    commit_head_sha: str | None = None
    draft: bool = False


async def upsert_pull_request(
    db: AsyncSession,
    org_id: UUID,
    task_id: UUID,
    payload: PullRequestUpsertInput,
) -> LivingPullRequest:
    """Create or update the LivingPullRequest row attached to a task."""
    await _load_task(db, org_id, task_id)

    if payload.provider == LivingPrProvider.LOCAL:
        intended_state = LivingPrState.NONE
    else:
        intended_state = LivingPrState.DRAFT if payload.draft else LivingPrState.OPEN

    pr = await _load_pr(db, task_id)
    state_changed = False

    if pr is None:
        pr = LivingPullRequest(
            task_id=task_id,
            org_id=org_id,
            branch_name=payload.branch_name,
            base_branch=payload.base_branch,
            provider=payload.provider,
            pr_number=payload.pr_number,
            pr_url=payload.pr_url,
            commit_head_sha=payload.commit_head_sha,
            pr_state=intended_state,
        )
        db.add(pr)
        state_changed = intended_state != LivingPrState.NONE
    else:
        pr.branch_name = payload.branch_name
        pr.base_branch = payload.base_branch
        pr.provider = payload.provider
        if payload.pr_number is not None:
            pr.pr_number = payload.pr_number
        if payload.pr_url is not None:
            pr.pr_url = payload.pr_url
        if payload.commit_head_sha is not None:
            pr.commit_head_sha = payload.commit_head_sha
        if pr.pr_state != intended_state:
            pr.pr_state = intended_state
            state_changed = True
        pr.updated_at = datetime.now(timezone.utc)

    await db.flush()

    if state_changed:
        await bus.emit(
            PrStateChangedEvent(
                db=db,
                org_id=org_id,
                task_id=task_id,
                pr_state=pr.pr_state.value,
                merge_state_status=pr.merge_state_status.value,
                pr_number=pr.pr_number,
            )
        )

    await db.commit()
    return pr


@dataclass
class PullRequestPatchInput:
    pr_state: LivingPrState | None = None
    merge_state_status: LivingMergeStateStatus | None = None
    commit_head_sha: str | None = None


async def patch_pull_request(
    db: AsyncSession,
    org_id: UUID,
    task_id: UUID,
    payload: PullRequestPatchInput,
) -> LivingPullRequest:
    """Partial update from a polling cycle (pr_state / merge_state_status / commit_head_sha)."""
    await _load_task(db, org_id, task_id)

    pr = await _load_pr(db, task_id)
    if pr is None:
        raise PrServiceError(
            PrServiceErrorCode.PR_NOT_FOUND,
            "Pull request not found - call upsert (action=link) first.",
            http_status=404,
        )

    state_changed = False
    if payload.pr_state is not None and payload.pr_state != pr.pr_state:
        pr.pr_state = payload.pr_state
        state_changed = True
    if (
        payload.merge_state_status is not None
        and payload.merge_state_status != pr.merge_state_status
    ):
        pr.merge_state_status = payload.merge_state_status
    if payload.commit_head_sha is not None:
        pr.commit_head_sha = payload.commit_head_sha
    pr.updated_at = datetime.now(timezone.utc)

    await db.flush()

    if state_changed:
        await bus.emit(
            PrStateChangedEvent(
                db=db,
                org_id=org_id,
                task_id=task_id,
                pr_state=pr.pr_state.value,
                merge_state_status=pr.merge_state_status.value,
                pr_number=pr.pr_number,
            )
        )

    await db.commit()
    return pr


@dataclass
class MergeRecordInput:
    merge_strategy: LivingMergeStrategy
    merged_commit_sha: str


async def record_merge(
    db: AsyncSession,
    org_id: UUID,
    task_id: UUID,
    payload: MergeRecordInput,
) -> LivingPullRequest:
    """Record the merge happened. Advances task to DONE if not already terminal."""
    task = await _load_task(db, org_id, task_id)

    pr = await _load_pr(db, task_id)
    if pr is None:
        raise PrServiceError(
            PrServiceErrorCode.PR_NOT_FOUND,
            "Pull request not found - call upsert (action=link) first.",
            http_status=404,
        )

    now = datetime.now(timezone.utc)
    pr.pr_state = LivingPrState.MERGED
    pr.merge_strategy = payload.merge_strategy
    pr.commit_head_sha = payload.merged_commit_sha
    pr.merged_at = now
    pr.updated_at = now

    if task.status not in (LivingTaskStatus.DONE, LivingTaskStatus.CANCELLED):
        task.status = LivingTaskStatus.DONE
        if task.completed_at is None:
            task.completed_at = now

    await db.flush()
    await bus.emit(
        MergeCompletedEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            merge_strategy=payload.merge_strategy.value,
            merged_commit_sha=payload.merged_commit_sha,
            provider=pr.provider.value,
        )
    )
    await db.commit()
    return pr


async def get_pr_for_task(
    db: AsyncSession,
    org_id: UUID,
    task_id: UUID,
) -> LivingPullRequest | None:
    """Return the PR attached to this task (or None). Cross-org safe."""
    await _load_task(db, org_id, task_id)
    return await _load_pr(db, task_id)
