"""Automatic task status transitions based on linked PR state changes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.audit import log_action
from src.shared.models import Edge, Entity
from src.shared.types import TASK_STATUS_PIPELINE, EdgeType, EntityType, PRState, TaskStatus

logger = logging.getLogger(__name__)


# PR state -> task status mapping
# Only advance tasks forward in the pipeline, never backward
def _status_rank(status: str) -> int:
    try:
        return TASK_STATUS_PIPELINE.index(status)
    except ValueError:
        return -1


async def propagate_pr_state_to_tasks(
    db: AsyncSession,
    pr_entity_id: UUID,
) -> list[UUID]:
    """Check the PR entity's state and advance any linked tasks accordingly.

    Rules:
    - PR opened (state=open, draft=False) -> task moves to at least in_progress
    - PR has review activity (review_state set) -> task moves to at least in_review
    - PR merged (merged=True) -> task moves to merged
    - PR closed without merge (state=closed, merged=False) -> no change

    Only advances tasks forward, never moves them backward.
    Returns list of task entity IDs that were updated.
    """
    pr = await db.get(Entity, pr_entity_id)
    if not pr or pr.type != EntityType.COMMIT_PR:
        return []

    props = pr.properties or {}
    pr_state = props.get("state", "")
    pr_merged = props.get("merged", False)
    pr_draft = props.get("draft", False)

    review_state = props.get("review_state")  # "approved", "changes_requested", "commented"
    has_reviewers = bool(props.get("requested_reviewers"))

    # Determine the target task status based on PR state
    target_status: str | None = None

    if pr_merged:
        target_status = TaskStatus.MERGED
    elif pr_state == PRState.OPEN and not pr_draft and (review_state or has_reviewers):
        # PR has review activity or requested reviewers - move to in_review
        target_status = TaskStatus.IN_REVIEW
    elif pr_state == PRState.OPEN and not pr_draft:
        target_status = TaskStatus.IN_PROGRESS

    if not target_status:
        return []

    # Find tasks linked to this PR via SHIPS_TO edges (PR -> task or task -> PR)
    edge_result = await db.execute(
        select(Edge).where(
            Edge.org_id == pr.org_id,
            Edge.type == EdgeType.SHIPS_TO,
            (Edge.from_entity_id == pr_entity_id) | (Edge.to_entity_id == pr_entity_id),
        )
    )
    edges = list(edge_result.scalars().all())

    if not edges:
        return []

    # Collect linked task IDs
    task_ids: set[UUID] = set()
    for edge in edges:
        other_id = edge.to_entity_id if edge.from_entity_id == pr_entity_id else edge.from_entity_id
        task_ids.add(other_id)

    # Load task entities and advance their status
    updated: list[UUID] = []
    for task_id in task_ids:
        task = await db.get(Entity, task_id)
        if not task or task.type != EntityType.TASK:
            continue

        task_props = dict(task.properties or {})
        current_status = task_props.get("status", TaskStatus.TODO)

        # Only advance forward, never backward
        if _status_rank(target_status) > _status_rank(current_status):
            task_props["status"] = target_status
            task.properties = task_props
            task.updated_at = datetime.now(timezone.utc)
            updated.append(task_id)
            logger.info(
                "Auto-advanced task %s from '%s' to '%s' (PR %s %s)",
                task_id,
                current_status,
                target_status,
                pr_entity_id,
                "merged" if pr_merged else "opened",
            )
            # Log activity for the transition
            await log_action(
                db,
                org_id=task.org_id,
                action="task_status_changed",
                resource_type="task",
                resource_id=task_id,
                details={
                    "old_status": current_status,
                    "new_status": target_status,
                    "trigger": "pr_state_change",
                    "pr_entity_id": str(pr_entity_id),
                    "pr_name": pr.canonical_name,
                    "task_name": task.canonical_name,
                },
            )

    if updated:
        await db.flush()

    return updated


async def preview_pr_task_transition(
    db: AsyncSession,
    pr_entity_id: UUID,
    task_entity_id: UUID,
) -> dict | None:
    """Preview what status transition would occur without applying it.

    Uses the same PR-state-to-status rules as propagate_pr_state_to_tasks
    but performs no writes. Returns a dict with transition details or None
    if no transition would occur.
    """
    pr = await db.get(Entity, pr_entity_id)
    if not pr or pr.type != EntityType.COMMIT_PR:
        return None

    task = await db.get(Entity, task_entity_id)
    if not task or task.type != EntityType.TASK:
        return None

    props = pr.properties or {}
    pr_merged = props.get("merged", False)
    pr_state = props.get("state", "")
    pr_draft = props.get("draft", False)
    review_state = props.get("review_state")
    has_reviewers = bool(props.get("requested_reviewers"))

    target_status: str | None = None
    if pr_merged:
        target_status = TaskStatus.MERGED
    elif pr_state == PRState.OPEN and not pr_draft and (review_state or has_reviewers):
        target_status = TaskStatus.IN_REVIEW
    elif pr_state == PRState.OPEN and not pr_draft:
        target_status = TaskStatus.IN_PROGRESS

    if not target_status:
        return None

    task_props = task.properties or {}
    current_status = task_props.get("status", TaskStatus.TODO)

    if _status_rank(target_status) <= _status_rank(current_status):
        return None

    return {
        "should_transition": True,
        "current_status": current_status,
        "target_status": target_status,
        "pr_name": pr.canonical_name,
        "task_name": task.canonical_name,
    }
