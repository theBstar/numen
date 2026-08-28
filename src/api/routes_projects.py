"""Project management routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.rbac import GOALS_ROLES, require_role
from src.api.schemas import (
    ErrorResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectTaskListResponse,
    ProjectUpdateRequest,
)
from src.graph import (
    delete_edges,
    find_person_by_email,
    get_connected_entity_ids,
    get_entity,
    get_project_stats,
    get_project_tasks,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.shared.audit import log_action_safely
from src.shared.models import Entity, Organization, OrgMember
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    ProjectStatus,
    SourceType,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/orgs/{org_id}/projects",
    tags=["projects"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


def _entity_to_project_response(
    entity: Entity,
    task_count: int,
    tasks_done: int,
    goal_ids: list[UUID],
) -> ProjectResponse:
    """Convert an Entity (type=PROJECT) to a ProjectResponse."""
    return ProjectResponse(
        id=entity.id,
        name=entity.canonical_name,
        description=entity.properties.get("description"),
        status=entity.properties.get("status", "planning"),
        owner=entity.properties.get("owner_email"),
        start_date=entity.properties.get("start_date"),
        end_date=entity.properties.get("end_date"),
        task_count=task_count,
        tasks_done=tasks_done,
        goal_ids=goal_ids,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


async def _get_project_goal_ids(db: AsyncSession, project_id: UUID, org_id: UUID) -> list[UUID]:
    """Get all goal IDs linked to a project via TAGGED_TO edges."""
    return await get_connected_entity_ids(db, project_id, EdgeType.TAGGED_TO, direction="outgoing", org_id=org_id)


async def _wire_owner_edge(
    db: AsyncSession,
    org_id: UUID,
    project_id: UUID,
    owner_email: str,
) -> None:
    """Create an OWNS edge from the person entity to the project."""
    owner_entity = await find_person_by_email(db, org_id, owner_email)
    if owner_entity:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=owner_entity.id,
                to_entity_id=project_id,
                type=EdgeType.OWNS,
                weight=1.0,
                confidence=1.0,
            ),
        )


async def _wire_goal_edges(
    db: AsyncSession,
    org_id: UUID,
    project_id: UUID,
    goal_ids: list[UUID],
) -> None:
    """Create TAGGED_TO edges from the project to each goal."""
    for goal_id in goal_ids:
        goal = await get_entity(db, goal_id, org_id=org_id)
        if goal and goal.org_id == org_id and goal.type == EntityType.GOAL:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=project_id,
                    to_entity_id=goal_id,
                    type=EdgeType.TAGGED_TO,
                    weight=1.0,
                    confidence=1.0,
                ),
            )


async def _get_project_entity(db: AsyncSession, org_id: UUID, project_id: UUID) -> Entity:
    """Fetch a project entity or raise 404."""
    entity = await get_entity(db, project_id, org_id=org_id)
    if not entity or entity.org_id != org_id or entity.type != EntityType.PROJECT:
        raise HTTPException(status_code=404, detail="Project not found")
    return entity


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=ProjectResponse,
    summary="Create project",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def create_project(
    req: ProjectCreateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Create a new project with optional owner and goal links."""
    slug = req.name.lower().replace(" ", "-")

    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PROJECT,
            source=SourceType.MANUAL,
            source_ids={"manual": slug},
            canonical_name=req.name,
            properties={
                "description": req.description,
                "status": req.status,
                "owner_email": req.owner_email,
                "start_date": req.start_date,
                "end_date": req.end_date,
            },
        ),
    )
    if req.owner_email:
        await _wire_owner_edge(db, org_id, entity.id, req.owner_email)

    if req.goal_ids:
        await _wire_goal_edges(db, org_id, entity.id, req.goal_ids)

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=current_member.user_id,
        action="project.created",
        resource_type="project",
        resource_id=entity.id,
        details={"name": req.name, "status": req.status},
    )
    await db.commit()

    return _entity_to_project_response(entity, task_count=0, tasks_done=0, goal_ids=req.goal_ids)


@router.get(
    "",
    response_model=ProjectListResponse,
    summary="List projects",
)
async def list_projects(
    org_id: UUID = Path(...),
    status: str | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search by name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List all projects with optional status and search filters."""
    all_projects = await graph_list_entities(
        db,
        org_id,
        entity_type=EntityType.PROJECT,
        search=search,
        status=status,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    # Filter by status
    if status is not None:
        projects = [p for p in all_projects if (p.properties or {}).get("status") == status]
    else:
        projects = [
            p for p in all_projects if (p.properties or {}).get("status") != ProjectStatus.ARCHIVED
        ]

    total = len(projects)

    items = []
    for project in projects:
        stats = await get_project_stats(db, project.id, org_id=org_id)
        goal_ids = await _get_project_goal_ids(db, project.id, org_id)
        items.append(_entity_to_project_response(project, stats["total"], stats["done"], goal_ids))

    return ProjectListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Get project",
    responses={404: {"model": ErrorResponse}},
)
async def get_project(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Get project details including task counts and linked goals."""
    entity = await _get_project_entity(db, org_id, project_id)
    stats = await get_project_stats(db, project_id, org_id=org_id)
    goal_ids = await _get_project_goal_ids(db, project_id, org_id)

    return _entity_to_project_response(entity, stats["total"], stats["done"], goal_ids)


@router.put(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Update project",
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def update_project(
    req: ProjectUpdateRequest,
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Partially update a project's properties, owner, and goal links."""
    entity = await _get_project_entity(db, org_id, project_id)
    updates = req.model_dump(exclude_unset=True)

    # Build updated properties
    props = dict(entity.properties)
    for field in ("description", "status", "owner_email", "start_date", "end_date"):
        if field in updates:
            props[field] = updates[field]

    entity = await update_entity(
        db,
        project_id,
        org_id=org_id,
        canonical_name=updates.get("name"),
        properties=props,
    )

    # Re-wire OWNS edge if owner changed
    if "owner_email" in updates:
        await delete_edges(db, project_id, EdgeType.OWNS, direction="incoming")

        if updates["owner_email"]:
            await _wire_owner_edge(db, org_id, project_id, updates["owner_email"])

    # Re-wire TAGGED_TO edges if goal_ids changed
    if "goal_ids" in updates:
        await delete_edges(db, project_id, EdgeType.TAGGED_TO, direction="outgoing")
        await _wire_goal_edges(db, org_id, project_id, updates["goal_ids"] or [])

    await db.commit()

    stats = await get_project_stats(db, project_id, org_id=org_id)
    goal_ids = await _get_project_goal_ids(db, project_id, org_id)

    return _entity_to_project_response(entity, stats["total"], stats["done"], goal_ids)


@router.delete(
    "/{project_id}",
    response_model=ProjectResponse,
    summary="Archive project",
    responses={404: {"model": ErrorResponse}},
)
async def archive_project(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _: OrgMember = Depends(require_role(*GOALS_ROLES)),
):
    """Soft-delete a project by setting its status to 'archived'."""
    entity = await _get_project_entity(db, org_id, project_id)

    props = dict(entity.properties)
    props["status"] = ProjectStatus.ARCHIVED

    entity = await update_entity(db, project_id, org_id=org_id, properties=props)

    await db.commit()

    stats = await get_project_stats(db, project_id, org_id=org_id)
    goal_ids = await _get_project_goal_ids(db, project_id, org_id)

    return _entity_to_project_response(entity, stats["total"], stats["done"], goal_ids)


@router.get(
    "/{project_id}/tasks",
    response_model=ProjectTaskListResponse,
    summary="List project tasks",
    responses={404: {"model": ErrorResponse}},
)
async def list_project_tasks(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    status: str | None = Query(None, description="Filter tasks by status"),
    db: AsyncSession = Depends(get_db),
):
    """List all tasks belonging to a project, optionally filtered by status."""
    from src.api.routes_tasks import _build_task_response

    await _get_project_entity(db, org_id, project_id)

    tasks = await get_project_tasks(db, project_id, org_id=org_id)

    if status:
        tasks = [t for t in tasks if t.properties.get("status") == status]

    items = [await _build_task_response(db, t, org_id=org_id) for t in tasks]
    return ProjectTaskListResponse(items=items)
