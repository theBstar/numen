"""Sprint CRUD + task assignment routes."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.schemas import (
    ErrorResponse,
    SprintAddTasksRequest,
    SprintCreateRequest,
    SprintListResponse,
    SprintResponse,
    SprintUpdateRequest,
)
from src.graph import (
    get_connected_entity_ids,
    get_entities_by_ids,
    get_entity,
    get_entity_or_404,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.shared.models import Organization
from src.shared.types import EdgeCreate, EdgeType, EntityCreate, EntityType, SourceType, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/sprints",
    tags=["sprints"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


async def _build_sprint_response(db, entity, org_id: UUID) -> SprintResponse:
    """Build a SprintResponse from an Entity by resolving connected tasks."""
    props = entity.properties or {}

    # Get task IDs connected via CONTAINS edge (sprint -> task)
    task_ids = await get_connected_entity_ids(db, entity.id, EdgeType.CONTAINS, direction="outgoing", org_id=org_id)

    task_count = len(task_ids)
    story_points_total = 0
    story_points_done = 0

    if task_ids:
        tasks = await get_entities_by_ids(db, task_ids)
        for task in tasks:
            task_props = task.properties or {}
            sp = task_props.get("story_points", 0)
            if isinstance(sp, (int, float)):
                story_points_total += int(sp)
                if task_props.get("status") == TaskStatus.DONE:
                    story_points_done += int(sp)

    # Parse dates
    start_date_raw = props.get("start_date")
    start_date: date | None = None
    if start_date_raw:
        try:
            start_date = date.fromisoformat(start_date_raw)
        except (ValueError, TypeError):
            start_date = None

    end_date_raw = props.get("end_date")
    end_date: date | None = None
    if end_date_raw:
        try:
            end_date = date.fromisoformat(end_date_raw)
        except (ValueError, TypeError):
            end_date = None

    return SprintResponse(
        id=entity.id,
        name=entity.canonical_name,
        status=props.get("status", "planning"),
        start_date=start_date,
        end_date=end_date,
        goal=props.get("goal"),
        velocity_target=props.get("velocity_target"),
        task_count=task_count,
        story_points_total=story_points_total,
        story_points_done=story_points_done,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=SprintResponse,
    status_code=201,
    summary="Create sprint",
    responses={400: {"model": ErrorResponse}},
)
async def create_sprint(
    req: SprintCreateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Create a new sprint as an Entity with type=SPRINT."""
    properties: dict = {
        "status": "planning",
    }
    if req.start_date is not None:
        properties["start_date"] = req.start_date.isoformat()
    if req.end_date is not None:
        properties["end_date"] = req.end_date.isoformat()
    if req.goal is not None:
        properties["goal"] = req.goal
    if req.velocity_target is not None:
        properties["velocity_target"] = req.velocity_target

    sprint_entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.SPRINT,
            source=SourceType.MANUAL,
            source_ids={"manual": f"sprint-{req.name.lower().replace(' ', '-')}"},
            canonical_name=req.name,
            properties=properties,
        ),
    )

    await db.commit()
    return await _build_sprint_response(db, sprint_entity, org_id)


@router.get(
    "",
    response_model=SprintListResponse,
    summary="List sprints",
)
async def list_sprints(
    org_id: UUID = Path(...),
    status: str | None = Query(None, description="Filter by sprint status"),
    db: AsyncSession = Depends(get_db),
):
    """List sprints with optional status filter."""
    all_sprints = await graph_list_entities(
        db,
        org_id,
        entity_type=EntityType.SPRINT,
        limit=200,
    )

    sprints = all_sprints
    if status:
        sprints = [s for s in sprints if (s.properties or {}).get("status") == status]

    items = [await _build_sprint_response(db, s, org_id) for s in sprints]
    return SprintListResponse(items=items)


@router.get(
    "/{sprint_id}",
    response_model=SprintResponse,
    summary="Get sprint",
    responses={404: {"model": ErrorResponse}},
)
async def get_sprint(
    org_id: UUID = Path(...),
    sprint_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get a sprint with task summary."""
    entity = await get_entity_or_404(db, sprint_id, org_id=org_id, expected_type=EntityType.SPRINT)
    return await _build_sprint_response(db, entity, org_id)


@router.put(
    "/{sprint_id}",
    response_model=SprintResponse,
    summary="Update sprint",
    responses={404: {"model": ErrorResponse}},
)
async def update_sprint_route(
    req: SprintUpdateRequest,
    org_id: UUID = Path(...),
    sprint_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Update a sprint."""
    entity = await get_entity_or_404(db, sprint_id, org_id=org_id, expected_type=EntityType.SPRINT)

    props = dict(entity.properties or {})
    new_name: str | None = req.name

    if req.status is not None:
        props["status"] = req.status
    if req.start_date is not None:
        props["start_date"] = req.start_date.isoformat()
    if req.end_date is not None:
        props["end_date"] = req.end_date.isoformat()
    if req.goal is not None:
        props["goal"] = req.goal
    if req.velocity_target is not None:
        props["velocity_target"] = req.velocity_target

    entity = await update_entity(db, sprint_id, canonical_name=new_name, properties=props)

    await db.commit()
    return await _build_sprint_response(db, entity, org_id)


@router.post(
    "/{sprint_id}/tasks",
    response_model=SprintResponse,
    summary="Add tasks to sprint",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def add_tasks_to_sprint(
    req: SprintAddTasksRequest,
    org_id: UUID = Path(...),
    sprint_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Add tasks to a sprint by creating CONTAINS edges (sprint -> task)."""
    sprint = await get_entity_or_404(db, sprint_id, org_id=org_id, expected_type=EntityType.SPRINT)

    for task_id in req.task_ids:
        task = await get_entity(db, task_id)
        if not task or task.org_id != org_id or task.type != EntityType.TASK:
            raise HTTPException(
                status_code=400,
                detail=f"Task entity {task_id} not found in this org",
            )

        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=sprint_id,
                to_entity_id=task_id,
                type=EdgeType.CONTAINS,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual_sprint_assignment"}],
            ),
        )

    await db.commit()
    return await _build_sprint_response(db, sprint, org_id)


@router.delete(
    "/{sprint_id}/tasks/{task_id}",
    status_code=204,
    summary="Remove task from sprint",
    responses={404: {"model": ErrorResponse}},
)
async def remove_task_from_sprint(
    org_id: UUID = Path(...),
    sprint_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Remove a task from a sprint by deleting the CONTAINS edge."""
    await get_entity_or_404(db, sprint_id, org_id=org_id, expected_type=EntityType.SPRINT)

    # Delete the CONTAINS edge from sprint to task
    from src.graph import delete_edge_by_id, list_edges

    edges = await list_edges(
        db,
        org_id=org_id,
        from_entity_id=sprint_id,
        to_entity_id=task_id,
        edge_type=EdgeType.CONTAINS,
    )
    if not edges:
        raise HTTPException(status_code=404, detail="Task not in this sprint")

    for edge in edges:
        await delete_edge_by_id(db, edge.id)

    await db.commit()
    return None
