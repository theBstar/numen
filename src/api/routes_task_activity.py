"""Task activity and comments routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    CommentCreateRequest,
    CommentUpdateRequest,
    ErrorResponse,
    TaskActivityListResponse,
    TaskActivityResponse,
)
from src.graph import get_entity, get_entity_or_404
from src.shared.models import OrgMember, TaskActivity
from src.shared.types import EntityType

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/tasks/{task_id}",
    tags=["tasks"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


async def _build_activity_response(db: AsyncSession, activity: TaskActivity) -> TaskActivityResponse:
    """Build a TaskActivityResponse, resolving the actor name if possible."""
    actor_name: str | None = None
    if activity.actor_id:
        actor = await get_entity(db, activity.actor_id)
        if actor:
            actor_name = actor.canonical_name
    return TaskActivityResponse(
        id=activity.id,
        entity_id=activity.entity_id,
        activity_type=activity.activity_type,
        actor_id=activity.actor_id,
        actor_name=actor_name,
        content=activity.content,
        details=activity.details or {},
        created_at=activity.created_at,
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.get(
    "/activity",
    response_model=TaskActivityListResponse,
    summary="List task activity",
)
async def list_activity(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """List all activity for a task, ordered by created_at descending."""
    # Verify task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    result = await db.execute(
        select(TaskActivity)
        .where(
            TaskActivity.org_id == org_id,
            TaskActivity.entity_id == task_id,
        )
        .order_by(TaskActivity.created_at.desc())
    )
    activities = result.scalars().all()

    items = [await _build_activity_response(db, a) for a in activities]
    return TaskActivityListResponse(items=items)


@router.post(
    "/comments",
    response_model=TaskActivityResponse,
    status_code=201,
    summary="Add comment",
    responses={404: {"model": ErrorResponse}},
)
async def add_comment(
    req: CommentCreateRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a task."""
    # Verify task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    activity = TaskActivity(
        org_id=org_id,
        entity_id=task_id,
        activity_type="comment",
        actor_id=member.person_entity_id,
        content=req.content,
        details={},
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)

    return await _build_activity_response(db, activity)


@router.put(
    "/comments/{comment_id}",
    response_model=TaskActivityResponse,
    summary="Edit comment",
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def edit_comment(
    req: CommentUpdateRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Edit a comment. Only the author can edit their own comments."""
    result = await db.execute(
        select(TaskActivity).where(
            TaskActivity.id == comment_id,
            TaskActivity.org_id == org_id,
            TaskActivity.entity_id == task_id,
        )
    )
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Comment not found")

    if activity.activity_type != "comment":
        raise HTTPException(status_code=400, detail="Only comments can be edited")

    if activity.actor_id != member.person_entity_id:
        raise HTTPException(status_code=403, detail="Can only edit your own comments")

    activity.content = req.content
    await db.commit()
    await db.refresh(activity)

    return await _build_activity_response(db, activity)


@router.delete(
    "/comments/{comment_id}",
    status_code=204,
    summary="Delete comment",
    responses={404: {"model": ErrorResponse}},
)
async def delete_comment(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Delete a comment."""
    result = await db.execute(
        select(TaskActivity).where(
            TaskActivity.id == comment_id,
            TaskActivity.org_id == org_id,
            TaskActivity.entity_id == task_id,
        )
    )
    activity = result.scalar_one_or_none()
    if not activity:
        raise HTTPException(status_code=404, detail="Comment not found")

    await db.delete(activity)
    await db.commit()
    return None
