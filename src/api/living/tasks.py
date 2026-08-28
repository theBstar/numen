"""Living tasks API - CRUD + state-machine for living_task rows.

All routes scope by the authenticated principal's org_id. Cross-org reads
return 404 (never 403, never the data).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.shared.models import LivingTask
from src.shared.types import (
    AgentRuntime,
    LivingTaskStatus,
    is_legal_living_task_transition,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/living/tasks", tags=["living"])


# ── Schemas ──────────────────────────────────────────────────────────


class LivingTaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    runtime: AgentRuntime


class LivingTaskStatusPatch(BaseModel):
    status: LivingTaskStatus
    error_msg: str | None = None


class LivingTaskOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    description: str | None
    runtime: AgentRuntime
    status: LivingTaskStatus
    worktree_id: UUID | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    context_fetch_count: int
    error_msg: str | None


class LivingTaskListOut(BaseModel):
    items: list[LivingTaskOut]
    total: int
    page: int
    page_size: int


def _to_out(t: LivingTask) -> LivingTaskOut:
    return LivingTaskOut(
        id=t.id,
        org_id=t.org_id,
        name=t.name,
        description=t.description,
        runtime=t.runtime,
        status=t.status,
        worktree_id=t.worktree_id,
        created_at=t.created_at,
        started_at=t.started_at,
        completed_at=t.completed_at,
        context_fetch_count=t.context_fetch_count or 0,
        error_msg=t.error_msg,
    )


# ── Routes ───────────────────────────────────────────────────────────


@router.post("", response_model=LivingTaskOut, status_code=201)
async def create_task(
    body: LivingTaskCreate,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> LivingTaskOut:
    task = LivingTask(
        org_id=principal.org_id,
        name=body.name,
        description=body.description,
        runtime=body.runtime,
        status=LivingTaskStatus.QUEUED,
    )
    db.add(task)
    await db.flush()
    await db.commit()
    return _to_out(task)


@router.get("", response_model=LivingTaskListOut)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: LivingTaskStatus | None = None,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> LivingTaskListOut:
    where = [LivingTask.org_id == principal.org_id]
    if status is not None:
        where.append(LivingTask.status == status)

    total_row = await db.execute(select(func.count(LivingTask.id)).where(*where))
    total = int(total_row.scalar() or 0)

    offset = (page - 1) * page_size
    rows = await db.execute(
        select(LivingTask)
        .where(*where)
        .order_by(LivingTask.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = [_to_out(t) for t in rows.scalars().all()]
    return LivingTaskListOut(
        items=items, total=total, page=page, page_size=page_size
    )


@router.get("/{task_id}", response_model=LivingTaskOut)
async def get_task(
    task_id: UUID,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> LivingTaskOut:
    row = await db.execute(
        select(LivingTask).where(
            LivingTask.id == task_id, LivingTask.org_id == principal.org_id
        )
    )
    task = row.scalar_one_or_none()
    if task is None:
        # Cross-org leak protection: 404 (not 403, not the row).
        raise HTTPException(status_code=404, detail="Task not found")
    return _to_out(task)


@router.patch("/{task_id}/status", response_model=LivingTaskOut)
async def patch_status(
    task_id: UUID,
    body: LivingTaskStatusPatch,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> LivingTaskOut:
    row = await db.execute(
        select(LivingTask).where(
            LivingTask.id == task_id, LivingTask.org_id == principal.org_id
        )
    )
    task = row.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if not is_legal_living_task_transition(task.status, body.status):
        raise HTTPException(
            status_code=409,
            detail=(
                f"Illegal transition: {task.status.value} -> {body.status.value}"
            ),
        )

    now = datetime.now(timezone.utc)
    task.status = body.status
    if body.status == LivingTaskStatus.RUNNING and task.started_at is None:
        task.started_at = now
    if body.status in (
        LivingTaskStatus.DONE,
        LivingTaskStatus.FAILED,
        LivingTaskStatus.CANCELLED,
    ):
        task.completed_at = now
    if body.error_msg is not None:
        task.error_msg = body.error_msg
    await db.flush()
    await db.commit()
    return _to_out(task)
