"""Living Mac-app event ingest.

The Mac app POSTs lifecycle events here so the cloud event log mirrors the
local worktree state. Validation:
  - The task_id in the URL MUST belong to the requester's org (else 404).
  - The body kind MUST be one of the known Living event kinds.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.events import LivingTaskEvent, bus
from src.shared.models import LivingTask

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/living/tasks", tags=["living"])


# Kinds enumerated in the Living design doc data model.
ALLOWED_EVENT_KINDS = {
    "context_fetch",
    "session_start",
    "session_complete",
    "worktree_spawn",
    "worktree_archive",
    "agent_intervention",
}


class LivingEventIn(BaseModel):
    kind: str = Field(..., description="One of the allowed Living event kinds")
    payload: dict = Field(default_factory=dict)
    agent_id: UUID | None = None
    worktree_id: UUID | None = None


class LivingEventAck(BaseModel):
    ok: bool
    handlers_invoked: int


@router.post("/{task_id}/events", response_model=LivingEventAck, status_code=202)
async def ingest_event(
    task_id: UUID,
    body: LivingEventIn,
    principal: LivingPrincipal = Depends(get_living_principal),
    db: AsyncSession = Depends(get_db),
) -> LivingEventAck:
    if body.kind not in ALLOWED_EVENT_KINDS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unknown event kind: {body.kind}. Allowed: "
                f"{sorted(ALLOWED_EVENT_KINDS)}"
            ),
        )

    row = await db.execute(
        select(LivingTask).where(
            LivingTask.id == task_id, LivingTask.org_id == principal.org_id
        )
    )
    task = row.scalar_one_or_none()
    if task is None:
        # Either does not exist OR belongs to another org. Both -> 404.
        raise HTTPException(status_code=404, detail="Task not found")

    event = LivingTaskEvent(
        db=db,
        org_id=principal.org_id,
        task_id=task_id,
        kind=body.kind,
        payload=body.payload,
        agent_id=body.agent_id,
        worktree_id=body.worktree_id,
    )
    results = await bus.emit(event)

    # Bump fetch counter so the orchestrator UI can show "X context fetches".
    if body.kind == "context_fetch":
        task.context_fetch_count = (task.context_fetch_count or 0) + 1
        await db.flush()
    await db.commit()

    return LivingEventAck(ok=True, handlers_invoked=len(results))
