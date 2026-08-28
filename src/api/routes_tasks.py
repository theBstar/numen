"""Task CRUD routes - manual task lifecycle + coexistence with connector-synced tasks."""

from __future__ import annotations

import logging
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.events import track_task_created, track_task_status_changed
from src.api.dependencies import get_current_member, get_db, get_org
from src.api.schemas import (
    AiPromptResponse,
    ErrorResponse,
    SubtaskCreateRequest,
    TaskCreateRequest,
    TaskLinkRequest,
    TaskListResponse,
    TaskResponse,
    TaskUpdateRequest,
    TransitionPreviewResponse,
)
from src.graph import (
    delete_edges,
    find_person_by_email,
    get_connected_entity_ids,
    get_entities_via_edge,
    get_entity,
    get_entity_or_404,
    list_edges,
    replace_edges,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.shared.audit import log_action_safely
from src.shared.models import Entity, Organization, OrgMember
from src.shared.types import EdgeCreate, EdgeType, EntityCreate, EntityType, SourceType, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


async def _resolve_person_by_email(db: AsyncSession, org_id: UUID, email: str) -> Entity | None:
    """Find a Person entity by email.

    First checks OrgMember.person_entity_id, then falls back to the graph
    API's find_person_by_email (searches source_ids and properties).
    """
    # Strategy 1: Look up via OrgMember
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.email == email,
        )
    )
    member = result.scalar_one_or_none()
    if member and member.person_entity_id:
        person = await get_entity(db, member.person_entity_id)
        if person:
            return person

    # Strategy 2: Search Person entities via the graph API
    return await find_person_by_email(db, org_id, email)


async def _build_task_response(
    db: AsyncSession,
    entity: Entity,
    org_id: UUID | None = None,
) -> TaskResponse:
    """Build a TaskResponse from an Entity by resolving edges."""
    props = entity.properties or {}
    _oid = org_id or entity.org_id

    # Resolve assignee: find Person entities connected via ASSIGNED_TO (incoming)
    assignee_email: str | None = None
    assignee_persons = await get_entities_via_edge(
        db,
        entity.id,
        EdgeType.ASSIGNED_TO,
        direction="incoming",
        target_type=EntityType.PERSON,
        org_id=_oid,
    )
    if assignee_persons:
        person = assignee_persons[0]
        assignee_email = (person.properties or {}).get("email") or person.canonical_name

    # Resolve project_id: find CONTAINS edge where to_entity_id == task (incoming)
    project_id: UUID | None = None
    contains_edges = await list_edges(db, org_id=_oid, to_entity_id=entity.id, edge_type=EdgeType.CONTAINS)
    if contains_edges:
        project_id = contains_edges[0].from_entity_id

    # Resolve goal_ids: find TAGGED_TO edges where from_entity_id == task (outgoing)
    goal_ids: list[UUID] = await get_connected_entity_ids(
        db,
        entity.id,
        EdgeType.TAGGED_TO,
        direction="outgoing",
        org_id=_oid,
    )

    # Parse due_date
    due_date_raw = props.get("due_date")
    due_date: date | None = None
    if due_date_raw:
        try:
            due_date = date.fromisoformat(due_date_raw)
        except (ValueError, TypeError):
            due_date = None

    # Resolve parent_id (incoming PARENT_OF edge means this task is a subtask)
    parent_id: UUID | None = None
    parent_edges = await list_edges(db, org_id=_oid, to_entity_id=entity.id, edge_type=EdgeType.PARENT_OF)
    if parent_edges:
        parent_id = parent_edges[0].from_entity_id

    # Count subtasks (outgoing PARENT_OF edges)
    subtask_ids = await get_connected_entity_ids(
        db,
        entity.id,
        EdgeType.PARENT_OF,
        direction="outgoing",
        org_id=_oid,
    )

    return TaskResponse(
        id=entity.id,
        title=entity.canonical_name,
        description=props.get("description"),
        status=props.get("status", TaskStatus.TODO),
        priority=props.get("priority", "medium"),
        assignee=assignee_email,
        due_date=due_date,
        source=entity.source,
        project_id=project_id,
        goal_ids=goal_ids,
        labels=props.get("labels", []),
        story_points=props.get("story_points"),
        estimated_hours=props.get("estimated_hours"),
        parent_id=parent_id,
        subtask_count=len(subtask_ids),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=TaskResponse,
    status_code=201,
    summary="Create task",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_task(
    req: TaskCreateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Create a manual task and auto-wire edges.

    Automatically creates:
    - CONTAINS edge from project_id -> task (if project_id provided)
    - TAGGED_TO edges from task -> each goal_id (if goal_ids provided)
    - ASSIGNED_TO edge from person -> task (if assignee_email provided)
    """
    # Build properties dict
    properties: dict = {
        "status": req.status,
        "priority": req.priority,
        "labels": req.labels,
    }
    if req.description is not None:
        properties["description"] = req.description
    if req.due_date is not None:
        properties["due_date"] = req.due_date.isoformat()
    if req.story_points is not None:
        properties["story_points"] = req.story_points
    if req.estimated_hours is not None:
        properties["estimated_hours"] = req.estimated_hours

    # Create the task entity
    task_entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.TASK,
            source=SourceType.MANUAL,
            source_ids={"manual": f"task-{req.title.lower().replace(' ', '-')}"},
            canonical_name=req.title,
            properties=properties,
        ),
    )

    # Auto-wire CONTAINS edge: project -> task
    if req.project_id:
        project = await get_entity(db, req.project_id)
        if not project or project.org_id != org_id:
            raise HTTPException(
                status_code=400, detail=f"Project entity {req.project_id} not found"
            )
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.project_id,
                to_entity_id=task_entity.id,
                type=EdgeType.CONTAINS,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual_task_creation"}],
            ),
        )

    # Auto-wire TAGGED_TO edges: task -> goal
    for goal_id in req.goal_ids:
        goal = await get_entity(db, goal_id)
        if not goal or goal.org_id != org_id or goal.type != EntityType.GOAL:
            raise HTTPException(status_code=400, detail=f"Goal entity {goal_id} not found")
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=task_entity.id,
                to_entity_id=goal_id,
                type=EdgeType.TAGGED_TO,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual_task_creation"}],
            ),
        )

    # Auto-wire ASSIGNED_TO edge: person -> task
    if req.assignee_email:
        person = await _resolve_person_by_email(db, org_id, req.assignee_email)
        if person:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=person.id,
                    to_entity_id=task_entity.id,
                    type=EdgeType.ASSIGNED_TO,
                    weight=1.0,
                    confidence=1.0,
                    evidence=[{"source": "manual_task_creation"}],
                ),
            )
        else:
            logger.warning(f"Assignee person not found for email: {req.assignee_email}")

    await track_task_created(
        member_id=str(current_member.id),
        org_id=str(org_id),
        task_id=str(task_entity.id),
        origin="manual",
        project_id=str(req.project_id) if req.project_id else None,
        goal_id=str(req.goal_ids[0]) if req.goal_ids else None,
    )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="task.created",
        resource_type="task",
        resource_id=task_entity.id,
        details={"title": req.title, "status": req.status},
    )
    await db.commit()

    return await _build_task_response(db, task_entity, org_id=org_id)


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List tasks",
)
async def list_tasks(
    org_id: UUID = Path(...),
    status: str | None = Query(
        None, description="Filter by status: todo, in_progress, done, cancelled"
    ),
    priority: str | None = Query(
        None, description="Filter by priority: urgent, high, medium, low, none"
    ),
    assignee_email: str | None = Query(None, description="Filter by assignee email"),
    project_id: UUID | None = Query(None, description="Filter by project (via CONTAINS edge)"),
    goal_id: UUID | None = Query(None, description="Filter by goal (via TAGGED_TO edge)"),
    search: str | None = Query(None, description="Search task title"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List tasks with optional filters.

    Supports filtering by:
    - status, priority: direct property filters on the Entity
    - assignee_email: join through ASSIGNED_TO edge -> Person entity
    - project_id: join through CONTAINS edge (project -> task)
    - goal_id: join through TAGGED_TO edge (task -> goal)
    - search: case-insensitive substring match on canonical_name
    """
    # Query tasks from FalkorDB
    all_tasks = await graph_list_entities(
        db,
        org_id,
        entity_type=EntityType.TASK,
        search=search,
        status=status,
        limit=500,
    )

    # Exclude archived tasks by default
    tasks = [t for t in all_tasks if (t.properties or {}).get("status") != TaskStatus.ARCHIVED]

    # Filter by status
    if status:
        tasks = [t for t in tasks if (t.properties or {}).get("status") == status]

    # Filter by priority
    if priority:
        tasks = [t for t in tasks if (t.properties or {}).get("priority") == priority]

    # Filter by project_id (via CONTAINS edge: project -> task)
    if project_id:
        task_ids_in_project = await get_connected_entity_ids(
            db, project_id, EdgeType.CONTAINS, direction="outgoing", org_id=org_id
        )
        if not task_ids_in_project:
            return TaskListResponse(items=[], total=0, page=page, page_size=page_size)
        project_id_set = set(task_ids_in_project)
        tasks = [t for t in tasks if t.id in project_id_set]

    # Filter by goal_id (via TAGGED_TO edge: task -> goal)
    if goal_id:
        task_ids_for_goal = await get_connected_entity_ids(
            db, goal_id, EdgeType.TAGGED_TO, direction="incoming", org_id=org_id
        )
        if not task_ids_for_goal:
            return TaskListResponse(items=[], total=0, page=page, page_size=page_size)
        goal_id_set = set(task_ids_for_goal)
        tasks = [t for t in tasks if t.id in goal_id_set]

    # Filter by assignee_email (via ASSIGNED_TO edge: person -> task)
    if assignee_email:
        person = await _resolve_person_by_email(db, org_id, assignee_email)
        if person:
            task_ids_for_assignee = await get_connected_entity_ids(
                db, person.id, EdgeType.ASSIGNED_TO, direction="outgoing", org_id=org_id
            )
            if not task_ids_for_assignee:
                return TaskListResponse(items=[], total=0, page=page, page_size=page_size)
            assignee_id_set = set(task_ids_for_assignee)
            tasks = [t for t in tasks if t.id in assignee_id_set]
        else:
            return TaskListResponse(items=[], total=0, page=page, page_size=page_size)

    total = len(tasks)

    # Paginate
    start = (page - 1) * page_size
    entities = tasks[start : start + page_size]

    # Build responses (resolve edges for each task)
    items = [await _build_task_response(db, e, org_id=org_id) for e in entities]

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task",
    responses={404: {"model": ErrorResponse}},
)
async def get_task(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get task detail with linked entities (project, goals, assignee)."""
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)
    return await _build_task_response(db, entity, org_id=org_id)


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update task",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_task(
    req: TaskUpdateRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Update a task. Handles edge rewiring on assignee/project/goal changes.

    Edge rewiring logic:
    - assignee_email changed: delete old ASSIGNED_TO edge, create new one
    - project_id changed: delete old CONTAINS edge, create new one
    - goal_ids provided: delete ALL old TAGGED_TO edges, create new ones
    """
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    # Update scalar properties via update_entity
    props = dict(entity.properties or {})
    prior_status = props.get("status")
    new_name: str | None = req.title
    if req.description is not None:
        props["description"] = req.description
    if req.status is not None:
        props["status"] = req.status
    if req.priority is not None:
        props["priority"] = req.priority
    if req.due_date is not None:
        props["due_date"] = req.due_date.isoformat()
    if req.labels is not None:
        props["labels"] = req.labels
    if req.story_points is not None:
        props["story_points"] = req.story_points
    if req.estimated_hours is not None:
        props["estimated_hours"] = req.estimated_hours

    entity = await update_entity(db, task_id, org_id=org_id, canonical_name=new_name, properties=props)

    # Rewire ASSIGNED_TO edge on assignee change
    if req.assignee_email is not None:
        # Delete existing ASSIGNED_TO edges pointing to this task
        await delete_edges(db, task_id, edge_type=EdgeType.ASSIGNED_TO, direction="incoming")

        # Create new ASSIGNED_TO edge (if email is not empty)
        if req.assignee_email:
            person = await _resolve_person_by_email(db, org_id, req.assignee_email)
            if person:
                await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=person.id,
                        to_entity_id=task_id,
                        type=EdgeType.ASSIGNED_TO,
                        weight=1.0,
                        confidence=1.0,
                        evidence=[{"source": "manual_task_update"}],
                    ),
                )

    # Rewire CONTAINS edge on project change
    if req.project_id is not None:
        # Delete existing CONTAINS edges pointing to this task
        await delete_edges(db, task_id, edge_type=EdgeType.CONTAINS, direction="incoming")

        # Create new CONTAINS edge
        project = await get_entity(db, req.project_id)
        if not project or project.org_id != org_id:
            raise HTTPException(
                status_code=400, detail=f"Project entity {req.project_id} not found"
            )
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.project_id,
                to_entity_id=task_id,
                type=EdgeType.CONTAINS,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual_task_update"}],
            ),
        )

    # Rewire TAGGED_TO edges on goal_ids change
    if req.goal_ids is not None:
        # Validate all goal entities first
        for goal_id in req.goal_ids:
            goal = await get_entity(db, goal_id)
            if not goal or goal.org_id != org_id or goal.type != EntityType.GOAL:
                raise HTTPException(status_code=400, detail=f"Goal entity {goal_id} not found")

        # Atomically replace TAGGED_TO edges
        await replace_edges(
            db,
            task_id,
            EdgeType.TAGGED_TO,
            direction="outgoing",
            new_target_ids=req.goal_ids,
            org_id=org_id,
            evidence=[{"source": "manual_task_update"}],
        )

    status_changed = req.status is not None and req.status != prior_status
    audit_details: dict = {"title": req.title} if req.title else {}
    if status_changed:
        audit_details["old_status"] = str(prior_status) if prior_status else None
        audit_details["new_status"] = str(req.status)
    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="task.updated",
        resource_type="task",
        resource_id=task_id,
        details=audit_details,
    )
    await db.commit()
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    if status_changed:
        await track_task_status_changed(
            member_id=str(current_member.id),
            org_id=str(org_id),
            task_id=str(task_id),
            from_status=str(prior_status) if prior_status else "unknown",
            to_status=str(req.status),
        )

    return await _build_task_response(db, entity, org_id=org_id)


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete task",
    responses={404: {"model": ErrorResponse}},
)
async def delete_task(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Soft-delete a task by setting status to 'archived'.

    Does not remove the Entity or its edges - they remain for graph integrity
    and historical queries. Archived tasks are excluded from list queries by default.
    """
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    await update_entity(
        db,
        task_id,
        org_id=org_id,
        properties={"status": TaskStatus.ARCHIVED},
        merge_properties=True,
    )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="task.deleted",
        resource_type="task",
        resource_id=task_id,
        details={"title": entity.canonical_name},
    )
    await db.commit()
    return None


@router.post(
    "/{task_id}/link",
    response_model=TaskResponse,
    summary="Link task to entity",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def link_task(
    req: TaskLinkRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Link a task to another entity (goal, project, etc.).

    Edge directionality depends on edge_type:
    - TAGGED_TO: task -> entity (task tags to a goal)
    - CONTAINS: entity -> task (project contains this task)
    - Other types: task -> entity (default)
    """
    # Verify task exists
    task_entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    # Verify target entity exists and belongs to same org
    target_entity = await get_entity(db, req.entity_id)
    if not target_entity or target_entity.org_id != org_id:
        raise HTTPException(status_code=400, detail=f"Entity {req.entity_id} not found in this org")

    # Determine edge direction
    if req.edge_type == EdgeType.CONTAINS:
        from_id = req.entity_id
        to_id = task_id
    else:
        from_id = task_id
        to_id = req.entity_id

    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=from_id,
            to_entity_id=to_id,
            type=req.edge_type,
            weight=1.0,
            confidence=1.0,
            evidence=[{"source": "manual_task_link"}],
        ),
    )

    return await _build_task_response(db, task_entity, org_id=org_id)


@router.get(
    "/{task_id}/pr-transition-preview",
    response_model=TransitionPreviewResponse | None,
    summary="Preview task status transition from PR",
    responses={404: {"model": ErrorResponse}},
)
async def preview_pr_transition(
    task_id: UUID = Path(...),
    pr_entity_id: UUID = Query(..., description="PR entity ID to preview transition for"),
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Preview what status transition would occur if this PR is linked to the task.

    Returns transition details or null if no transition would happen.
    Uses the same forward-only rules as the automatic PR-to-task propagation.
    """
    from src.graph.task_transitions import preview_pr_task_transition

    # Validate task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    result = await preview_pr_task_transition(db, pr_entity_id, task_id)
    return result


@router.post(
    "/{task_id}/ai-prompt",
    response_model=AiPromptResponse,
    tags=["tasks"],
    summary="Generate an AI coding prompt for a task",
    responses={404: {"model": ErrorResponse}},
)
async def generate_ai_prompt(
    task_id: UUID = Path(...),
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Generate a rich, LLM-refined prompt with full task context.

    Gathers task details, linked goals, blocking chain, related PRs,
    project context, and urgency score, then refines via LLM into
    an actionable prompt for AI coding assistants.
    """
    from src.llm.prompt_generator import generate_task_prompt

    try:
        result = await generate_task_prompt(db, task_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    return AiPromptResponse(**result)


# ── Subtask endpoints ────────────────────────────────────────────────


@router.post(
    "/{task_id}/subtasks",
    response_model=TaskResponse,
    status_code=201,
    summary="Create subtask",
    responses={404: {"model": ErrorResponse}},
)
async def create_subtask(
    req: SubtaskCreateRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a subtask under a parent task.

    Creates a new Entity with type=TASK, source=MANUAL, then creates
    a PARENT_OF edge from the parent task to the child task.
    """
    # Verify parent task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    # Build subtask properties
    properties: dict = {
        "status": TaskStatus.TODO,
        "priority": req.priority,
        "labels": req.labels,
    }
    if req.description is not None:
        properties["description"] = req.description
    if req.due_date is not None:
        properties["due_date"] = req.due_date.isoformat()

    # Create the subtask entity
    subtask_entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.TASK,
            source=SourceType.MANUAL,
            source_ids={"manual": f"subtask-{req.title.lower().replace(' ', '-')}"},
            canonical_name=req.title,
            properties=properties,
        ),
    )

    # Create PARENT_OF edge: parent -> child
    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=task_id,
            to_entity_id=subtask_entity.id,
            type=EdgeType.PARENT_OF,
            weight=1.0,
            confidence=1.0,
            evidence=[{"source": "manual_subtask_creation"}],
        ),
    )

    # Wire assignee if provided
    if req.assignee_email:
        person = await _resolve_person_by_email(db, org_id, req.assignee_email)
        if person:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=person.id,
                    to_entity_id=subtask_entity.id,
                    type=EdgeType.ASSIGNED_TO,
                    weight=1.0,
                    confidence=1.0,
                    evidence=[{"source": "manual_subtask_creation"}],
                ),
            )

    return await _build_task_response(db, subtask_entity, org_id=org_id)


@router.get(
    "/{task_id}/subtasks",
    response_model=TaskListResponse,
    summary="List subtasks",
    responses={404: {"model": ErrorResponse}},
)
async def list_subtasks(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """List subtasks of a parent task (connected via outgoing PARENT_OF edges)."""
    # Verify parent task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    # Get entities connected via outgoing PARENT_OF edges
    subtask_entities = await get_entities_via_edge(
        db,
        task_id,
        EdgeType.PARENT_OF,
        direction="outgoing",
        target_type=EntityType.TASK,
        org_id=org_id,
    )

    items = [await _build_task_response(db, e, org_id=org_id) for e in subtask_entities]

    return TaskListResponse(
        items=items,
        total=len(items),
        page=1,
        page_size=len(items),
    )
