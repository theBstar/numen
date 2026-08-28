"""Goal & OKR CRUD routes."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.rbac import GOALS_ROLES, require_role
from src.api.schemas import (
    ErrorResponse,
    GoalCreateRequest,
    GoalLinkRequest,
    GoalLinkResponse,
    GoalListResponse,
    GoalProgressResponse,
    GoalResponse,
    GoalTreeResponse,
    GoalUnlinkResponse,
    GoalUpdateRequest,
)
from src.graph import (
    compute_goal_progress,
    delete_edge_by_id,
    delete_edges,
    find_person_by_email,
    get_connected_entity_ids,
    get_edge_by_triple,
    get_entities_via_edge,
    get_entity,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.graph import (
    get_goal_tree as _get_goal_tree,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.shared.audit import log_action_safely
from src.shared.models import Organization, OrgMember
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    GoalLevel,
    ProgressMode,
    ProjectStatus,
    SourceType,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/goals",
    tags=["goals"],
    dependencies=[Depends(get_current_member)],
)


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=GoalResponse,
    status_code=201,
    summary="Create goal",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_goal(
    req: GoalCreateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Create a new goal entity."""
    # Validate parent goal if provided
    if req.parent_goal_id:
        parent = await get_entity(db, req.parent_goal_id, org_id=org_id)
        if not parent or parent.org_id != org_id or parent.type != EntityType.GOAL:
            raise HTTPException(
                status_code=404,
                detail=f"Parent goal {req.parent_goal_id} not found in this organization",
            )
        if parent.properties.get("status") == ProjectStatus.ARCHIVED:
            raise HTTPException(
                status_code=400,
                detail="Cannot create a child of an archived goal",
            )

    # Serialize key results to dicts
    key_results_data = [kr.model_dump() for kr in req.key_results]

    # Build properties JSONB
    properties = {
        "level": req.level,
        "status": ProjectStatus.ACTIVE,
        "key_results": key_results_data,
        "target_value": req.target_value,
        "current_value": 0,
        "owner_email": req.owner_email,
        "time_bound_start": req.time_bound_start.isoformat() if req.time_bound_start else None,
        "time_bound_end": req.time_bound_end.isoformat() if req.time_bound_end else None,
        "progress_mode": ProgressMode.COMPUTED,
    }

    # Create the goal entity
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.GOAL,
            source=SourceType.MANUAL,
            source_ids={"manual": req.title.lower().replace(" ", "-")},
            canonical_name=req.title,
            properties=properties,
        ),
    )

    # Create PARENT_OF edge: parent -> child
    if req.parent_goal_id:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.parent_goal_id,
                to_entity_id=entity.id,
                type=EdgeType.PARENT_OF,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual", "action": "goal_created_as_child"}],
            ),
        )

    # Create OWNS edge: person -> goal
    if req.owner_email:
        person_entity = await find_person_by_email(db, org_id, req.owner_email)
        if person_entity:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=person_entity.id,
                    to_entity_id=entity.id,
                    type=EdgeType.OWNS,
                    weight=1.0,
                    confidence=1.0,
                    evidence=[{"source": "manual", "action": "goal_owner_assigned"}],
                ),
            )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="goal.created",
        resource_type="goal",
        resource_id=entity.id,
        details={"title": req.title, "level": req.level},
    )
    await db.commit()

    return GoalResponse(
        id=entity.id,
        title=entity.canonical_name,
        level=entity.properties.get("level", GoalLevel.TEAM),
        status=entity.properties.get("status", ProjectStatus.ACTIVE),
        key_results=entity.properties.get("key_results", []),
        target_value=entity.properties.get("target_value"),
        current_value=entity.properties.get("current_value"),
        computed_progress=None,
        owner=entity.properties.get("owner_email"),
        parent_goal_id=req.parent_goal_id,
        child_goal_ids=[],
        linked_project_ids=[],
        time_bound_start=_parse_iso_dt(entity.properties.get("time_bound_start")),
        time_bound_end=_parse_iso_dt(entity.properties.get("time_bound_end")),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get(
    "",
    response_model=GoalListResponse,
    summary="List goals",
    responses={404: {"model": ErrorResponse}},
)
async def list_goals(
    org_id: UUID = Path(...),
    level: str | None = Query(None, pattern="^(company|team|individual)$"),
    status: str | None = Query(None, pattern="^(active|archived)$"),
    db: AsyncSession = Depends(get_db),
):
    """List all goals for the org, optionally filtered by level and/or status."""
    effective_status = status if status else ProjectStatus.ACTIVE
    goals = await list_entities_for_goals(db, org_id, level=level, status=effective_status)

    responses = []
    for g in goals:
        parent_goal_id = await _get_parent_goal_id(db, g.id, org_id)
        child_goal_ids = await _get_child_goal_ids(db, g.id, org_id)
        linked_project_ids = await _get_linked_project_ids(db, g.id, org_id)

        responses.append(
            GoalResponse(
                id=g.id,
                title=g.canonical_name,
                level=g.properties.get("level", GoalLevel.TEAM),
                status=g.properties.get("status", ProjectStatus.ACTIVE),
                key_results=g.properties.get("key_results", []),
                target_value=g.properties.get("target_value"),
                current_value=g.properties.get("current_value"),
                computed_progress=None,
                owner=g.properties.get("owner_email"),
                parent_goal_id=parent_goal_id,
                child_goal_ids=child_goal_ids,
                linked_project_ids=linked_project_ids,
                time_bound_start=_parse_iso_dt(g.properties.get("time_bound_start")),
                time_bound_end=_parse_iso_dt(g.properties.get("time_bound_end")),
                created_at=g.created_at,
                updated_at=g.updated_at,
            )
        )

    return GoalListResponse(items=responses)


@router.get(
    "/tree",
    response_model=GoalTreeResponse,
    summary="Get goal tree",
)
async def get_goal_tree(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Return the full goal hierarchy as a nested tree."""
    tree = await _get_goal_tree(db, org_id)
    return GoalTreeResponse(items=tree)


@router.get(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Get goal",
    responses={404: {"model": ErrorResponse}},
)
async def get_goal(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get a single goal with its children, linked projects, and computed progress."""
    entity = await get_entity(db, goal_id, org_id=org_id)
    if not entity or entity.org_id != org_id or entity.type != EntityType.GOAL:
        raise HTTPException(status_code=404, detail="Goal not found")

    progress_data = await compute_goal_progress(db, goal_id, org_id=org_id)
    parent_goal_id = await _get_parent_goal_id(db, goal_id, org_id)
    child_goal_ids = await _get_child_goal_ids(db, goal_id, org_id)
    linked_project_ids = await _get_linked_project_ids(db, goal_id, org_id)

    return GoalResponse(
        id=entity.id,
        title=entity.canonical_name,
        level=entity.properties.get("level", GoalLevel.TEAM),
        status=entity.properties.get("status", ProjectStatus.ACTIVE),
        key_results=entity.properties.get("key_results", []),
        target_value=entity.properties.get("target_value"),
        current_value=entity.properties.get("current_value"),
        computed_progress=progress_data["task_completion_pct"],
        owner=entity.properties.get("owner_email"),
        parent_goal_id=parent_goal_id,
        child_goal_ids=child_goal_ids,
        linked_project_ids=linked_project_ids,
        time_bound_start=_parse_iso_dt(entity.properties.get("time_bound_start")),
        time_bound_end=_parse_iso_dt(entity.properties.get("time_bound_end")),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.put(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Update goal",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def update_goal(
    req: GoalUpdateRequest,
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Partial update of a goal's properties."""
    entity = await get_entity(db, goal_id, org_id=org_id)
    if not entity or entity.org_id != org_id or entity.type != EntityType.GOAL:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Build updated properties
    props = dict(entity.properties)

    if req.title is not None:
        pass  # handled via update_entity canonical_name below
    if req.level is not None:
        props["level"] = req.level
    if req.status is not None:
        props["status"] = req.status
    if req.key_results is not None:
        props["key_results"] = [kr.model_dump() for kr in req.key_results]
    if req.target_value is not None:
        props["target_value"] = req.target_value
    if req.current_value is not None:
        props["current_value"] = req.current_value
    if req.owner_email is not None:
        props["owner_email"] = req.owner_email
    if req.time_bound_start is not None:
        props["time_bound_start"] = req.time_bound_start.isoformat()
    if req.time_bound_end is not None:
        props["time_bound_end"] = req.time_bound_end.isoformat()

    entity = await update_entity(
        db,
        goal_id,
        org_id=org_id,
        canonical_name=req.title,
        properties=props,
    )

    # Handle parent_goal_id change
    if req.parent_goal_id is not None:
        parent = await get_entity(db, req.parent_goal_id, org_id=org_id)
        if not parent or parent.org_id != org_id or parent.type != EntityType.GOAL:
            raise HTTPException(
                status_code=404,
                detail=f"Parent goal {req.parent_goal_id} not found",
            )

        if req.parent_goal_id == goal_id:
            raise HTTPException(
                status_code=400,
                detail="A goal cannot be its own parent",
            )

        # Remove existing PARENT_OF edges pointing to this goal
        await delete_edges(db, goal_id, EdgeType.PARENT_OF, direction="incoming")

        # Create new PARENT_OF edge
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.parent_goal_id,
                to_entity_id=goal_id,
                type=EdgeType.PARENT_OF,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual", "action": "goal_parent_updated"}],
            ),
        )

    # Handle owner_email change
    if req.owner_email is not None:
        await delete_edges(db, goal_id, EdgeType.OWNS, direction="incoming")

        person_entity = await find_person_by_email(db, org_id, req.owner_email)
        if person_entity:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=person_entity.id,
                    to_entity_id=goal_id,
                    type=EdgeType.OWNS,
                    weight=1.0,
                    confidence=1.0,
                    evidence=[{"source": "manual", "action": "goal_owner_updated"}],
                ),
            )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="goal.updated",
        resource_type="goal",
        resource_id=goal_id,
        details={"title": req.title} if req.title else {},
    )
    await db.commit()

    parent_goal_id = await _get_parent_goal_id(db, goal_id, org_id)
    child_goal_ids = await _get_child_goal_ids(db, goal_id, org_id)
    linked_project_ids = await _get_linked_project_ids(db, goal_id, org_id)

    return GoalResponse(
        id=entity.id,
        title=entity.canonical_name,
        level=entity.properties.get("level", GoalLevel.TEAM),
        status=entity.properties.get("status", ProjectStatus.ACTIVE),
        key_results=entity.properties.get("key_results", []),
        target_value=entity.properties.get("target_value"),
        current_value=entity.properties.get("current_value"),
        computed_progress=None,
        owner=entity.properties.get("owner_email"),
        parent_goal_id=parent_goal_id,
        child_goal_ids=child_goal_ids,
        linked_project_ids=linked_project_ids,
        time_bound_start=_parse_iso_dt(entity.properties.get("time_bound_start")),
        time_bound_end=_parse_iso_dt(entity.properties.get("time_bound_end")),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.delete(
    "/{goal_id}",
    response_model=GoalResponse,
    summary="Delete goal",
    responses={404: {"model": ErrorResponse}},
)
async def delete_goal(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _: OrgMember = Depends(require_role(*GOALS_ROLES)),
):
    """Soft-delete a goal by setting its status to 'archived'."""
    entity = await get_entity(db, goal_id, org_id=org_id)
    if not entity or entity.org_id != org_id or entity.type != EntityType.GOAL:
        raise HTTPException(status_code=404, detail="Goal not found")

    props = dict(entity.properties)
    props["status"] = ProjectStatus.ARCHIVED

    entity = await update_entity(db, goal_id, org_id=org_id, properties=props)

    await db.commit()

    parent_goal_id = await _get_parent_goal_id(db, goal_id, org_id)
    child_goal_ids = await _get_child_goal_ids(db, goal_id, org_id)
    linked_project_ids = await _get_linked_project_ids(db, goal_id, org_id)

    return GoalResponse(
        id=entity.id,
        title=entity.canonical_name,
        level=entity.properties.get("level", GoalLevel.TEAM),
        status=ProjectStatus.ARCHIVED,
        key_results=entity.properties.get("key_results", []),
        target_value=entity.properties.get("target_value"),
        current_value=entity.properties.get("current_value"),
        computed_progress=None,
        owner=entity.properties.get("owner_email"),
        parent_goal_id=parent_goal_id,
        child_goal_ids=child_goal_ids,
        linked_project_ids=linked_project_ids,
        time_bound_start=_parse_iso_dt(entity.properties.get("time_bound_start")),
        time_bound_end=_parse_iso_dt(entity.properties.get("time_bound_end")),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get(
    "/{goal_id}/progress",
    response_model=GoalProgressResponse,
    summary="Get goal progress",
    responses={404: {"model": ErrorResponse}},
)
async def get_goal_progress(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Compute progress for a goal from its linked tasks."""
    entity = await get_entity(db, goal_id, org_id=org_id)
    if not entity or entity.org_id != org_id or entity.type != EntityType.GOAL:
        raise HTTPException(status_code=404, detail="Goal not found")

    progress = await compute_goal_progress(db, goal_id, org_id=org_id)

    return GoalProgressResponse(
        goal_id=goal_id,
        total_tasks=progress["total_tasks"],
        tasks_done=progress["tasks_done"],
        computed_progress=progress["computed_progress"],
        key_results_progress=progress["key_results_progress"],
    )


@router.post(
    "/{goal_id}/link",
    response_model=GoalLinkResponse,
    status_code=201,
    summary="Link entity to goal",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def link_entity_to_goal(
    req: GoalLinkRequest,
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Link an entity to a goal via a TAGGED_TO edge."""
    # Verify goal exists
    goal = await get_entity(db, goal_id, org_id=org_id)
    if not goal or goal.org_id != org_id or goal.type != EntityType.GOAL:
        raise HTTPException(status_code=404, detail="Goal not found")

    # Verify target entity exists in same org
    target = await get_entity(db, req.entity_id, org_id=org_id)
    if not target or target.org_id != org_id:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Prevent linking a goal to itself
    if req.entity_id == goal_id:
        raise HTTPException(status_code=400, detail="Cannot link a goal to itself")

    edge = await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=req.entity_id,
            to_entity_id=goal_id,
            type=EdgeType.TAGGED_TO,
            weight=1.0,
            confidence=1.0,
            evidence=[{"source": "manual", "action": "entity_linked_to_goal"}],
        ),
    )

    await db.commit()

    return {
        "status": "linked",
        "edge_id": str(edge.id),
        "goal_id": str(goal_id),
        "entity_id": str(req.entity_id),
    }


@router.delete(
    "/{goal_id}/link/{entity_id}",
    response_model=GoalUnlinkResponse,
    status_code=200,
    summary="Unlink entity from goal",
    responses={404: {"model": ErrorResponse}},
)
async def unlink_entity_from_goal(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Remove a TAGGED_TO edge between an entity and a goal."""
    edge = await get_edge_by_triple(db, entity_id, goal_id, EdgeType.TAGGED_TO)
    if not edge:
        raise HTTPException(status_code=404, detail="Link not found")

    await delete_edge_by_id(db, edge.id)
    await db.commit()

    return {"status": "unlinked", "goal_id": str(goal_id), "entity_id": str(entity_id)}


# ── Helper functions ──────────────────────────────────────────────────


async def list_entities_for_goals(
    db: AsyncSession,
    org_id: UUID,
    *,
    level: str | None = None,
    status: str | None = None,
) -> list:
    """List goal entities with optional level and status filtering."""
    goals = await graph_list_entities(db, org_id, entity_type=EntityType.GOAL, status=status, limit=500)

    if level:
        goals = [g for g in goals if (g.properties or {}).get("level") == level]

    return goals


async def _get_parent_goal_id(db: AsyncSession, goal_id: UUID, org_id: UUID) -> UUID | None:
    """Find the parent goal of the given goal via PARENT_OF edge."""
    parent_ids = await get_connected_entity_ids(db, goal_id, EdgeType.PARENT_OF, direction="incoming", org_id=org_id)
    return parent_ids[0] if parent_ids else None


async def _get_child_goal_ids(db: AsyncSession, goal_id: UUID, org_id: UUID) -> list[UUID]:
    """Find child goals via PARENT_OF edges where this goal is the parent."""
    return await get_connected_entity_ids(db, goal_id, EdgeType.PARENT_OF, direction="outgoing", org_id=org_id)


async def _get_linked_project_ids(db: AsyncSession, goal_id: UUID, org_id: UUID) -> list[UUID]:
    """Find projects linked to this goal via TAGGED_TO edges."""
    entities = await get_entities_via_edge(
        db,
        goal_id,
        EdgeType.TAGGED_TO,
        direction="incoming",
        target_type=EntityType.PROJECT,
        org_id=org_id,
    )
    return [e.id for e in entities]


def _parse_iso_dt(value: str | None) -> datetime | None:
    """Parse an ISO datetime string from JSONB properties, or return None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
