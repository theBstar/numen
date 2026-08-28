"""Task templates CRUD + apply routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.schemas import (
    ErrorResponse,
    TaskResponse,
    TaskTemplateCreateRequest,
    TaskTemplateListResponse,
    TaskTemplateResponse,
    TaskTemplateUpdateRequest,
)
from src.graph import upsert_edge, upsert_entity
from src.shared.models import Organization, OrgMember, TaskTemplate
from src.shared.types import EdgeCreate, EdgeType, EntityCreate, EntityType, SourceType, TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/templates",
    tags=["templates"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


def _template_to_response(t: TaskTemplate) -> TaskTemplateResponse:
    """Build a TaskTemplateResponse from a TaskTemplate model."""
    return TaskTemplateResponse(
        id=t.id,
        name=t.name,
        description=t.description,
        default_properties=t.default_properties or {},
        subtask_titles=t.subtask_titles or [],
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=TaskTemplateListResponse,
    summary="List templates",
)
async def list_templates(
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """List all task templates for the organization."""
    result = await db.execute(
        select(TaskTemplate).where(TaskTemplate.org_id == org_id).order_by(TaskTemplate.created_at.desc())
    )
    templates = result.scalars().all()

    items = [_template_to_response(t) for t in templates]
    return TaskTemplateListResponse(items=items)


@router.post(
    "",
    response_model=TaskTemplateResponse,
    status_code=201,
    summary="Create template",
    responses={400: {"model": ErrorResponse}},
)
async def create_template(
    req: TaskTemplateCreateRequest,
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Create a new task template."""
    template = TaskTemplate(
        org_id=org_id,
        name=req.name,
        description=req.description,
        default_properties=req.default_properties,
        subtask_titles=req.subtask_titles,
        created_by=member.id,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)

    return _template_to_response(template)


@router.put(
    "/{template_id}",
    response_model=TaskTemplateResponse,
    summary="Update template",
    responses={404: {"model": ErrorResponse}},
)
async def update_template(
    req: TaskTemplateUpdateRequest,
    org_id: UUID = Path(...),
    template_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Update a task template."""
    result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.id == template_id,
            TaskTemplate.org_id == org_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    if req.name is not None:
        template.name = req.name
    if req.description is not None:
        template.description = req.description
    if req.default_properties is not None:
        template.default_properties = req.default_properties
    if req.subtask_titles is not None:
        template.subtask_titles = req.subtask_titles

    await db.commit()
    await db.refresh(template)

    return _template_to_response(template)


@router.delete(
    "/{template_id}",
    status_code=204,
    summary="Delete template",
    responses={404: {"model": ErrorResponse}},
)
async def delete_template(
    org_id: UUID = Path(...),
    template_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Delete a task template."""
    result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.id == template_id,
            TaskTemplate.org_id == org_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    await db.delete(template)
    await db.commit()
    return None


@router.post(
    "/{template_id}/apply",
    response_model=TaskResponse,
    status_code=201,
    summary="Apply template",
    responses={404: {"model": ErrorResponse}},
)
async def apply_template(
    org_id: UUID = Path(...),
    template_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Create a task from a template, including subtasks with PARENT_OF edges."""
    result = await db.execute(
        select(TaskTemplate).where(
            TaskTemplate.id == template_id,
            TaskTemplate.org_id == org_id,
        )
    )
    template = result.scalar_one_or_none()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    # Build properties from template defaults
    default_props = dict(template.default_properties or {})
    properties = {
        "status": default_props.pop("status", TaskStatus.TODO),
        "priority": default_props.pop("priority", "medium"),
        "labels": default_props.pop("labels", []),
        **default_props,
    }
    if template.description:
        properties["description"] = template.description

    # Create the parent task entity
    parent_task = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.TASK,
            source=SourceType.MANUAL,
            source_ids={"manual": f"template-{template.name.lower().replace(' ', '-')}"},
            canonical_name=template.name,
            properties=properties,
        ),
    )

    # Create subtask entities and PARENT_OF edges
    subtask_titles = template.subtask_titles or []
    for title in subtask_titles:
        subtask = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.TASK,
                source=SourceType.MANUAL,
                source_ids={"manual": f"subtask-{title.lower().replace(' ', '-')}"},
                canonical_name=title,
                properties={
                    "status": TaskStatus.TODO,
                    "priority": "medium",
                    "labels": [],
                },
            ),
        )

        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=parent_task.id,
                to_entity_id=subtask.id,
                type=EdgeType.PARENT_OF,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "template_apply"}],
            ),
        )

    await db.commit()

    # Build response (inline to avoid circular import)
    props = parent_task.properties or {}
    from datetime import date as date_type

    due_date_raw = props.get("due_date")
    due_date: date_type | None = None
    if due_date_raw:
        try:
            due_date = date_type.fromisoformat(due_date_raw)
        except (ValueError, TypeError):
            due_date = None

    return TaskResponse(
        id=parent_task.id,
        title=parent_task.canonical_name,
        description=props.get("description"),
        status=props.get("status", TaskStatus.TODO),
        priority=props.get("priority", "medium"),
        assignee=None,
        due_date=due_date,
        source=parent_task.source,
        project_id=None,
        goal_ids=[],
        labels=props.get("labels", []),
        created_at=parent_task.created_at,
        updated_at=parent_task.updated_at,
    )
