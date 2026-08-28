"""Saved views CRUD routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    ErrorResponse,
    SavedViewCreateRequest,
    SavedViewListResponse,
    SavedViewResponse,
    SavedViewUpdateRequest,
)
from src.shared.models import OrgMember, SavedView

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/views",
    tags=["views"],
    dependencies=[Depends(get_current_member)],
)


# ── Routes ────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=SavedViewListResponse,
    summary="List saved views",
)
async def list_saved_views(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """List saved views for the current member (own views + shared views)."""
    result = await db.execute(
        select(SavedView)
        .where(
            SavedView.org_id == org_id,
            or_(
                SavedView.member_id == member.id,
                SavedView.is_shared.is_(True),
            ),
        )
        .order_by(SavedView.created_at.desc())
    )
    views = result.scalars().all()

    items = [
        SavedViewResponse(
            id=v.id,
            name=v.name,
            entity_type=v.entity_type,
            filters=v.filters or {},
            sort_config=v.sort_config or {},
            view_mode=v.view_mode or "list",
            group_by=v.group_by,
            is_default=v.is_default,
            is_shared=v.is_shared,
            created_at=v.created_at,
            updated_at=v.updated_at,
        )
        for v in views
    ]
    return SavedViewListResponse(items=items)


@router.post(
    "",
    response_model=SavedViewResponse,
    status_code=201,
    summary="Create saved view",
    responses={400: {"model": ErrorResponse}},
)
async def create_saved_view(
    req: SavedViewCreateRequest,
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Create a new saved view."""
    view = SavedView(
        org_id=org_id,
        member_id=member.id,
        name=req.name,
        entity_type=req.entity_type,
        filters=req.filters,
        sort_config=req.sort_config,
        view_mode=req.view_mode,
        group_by=req.group_by,
        is_default=req.is_default,
        is_shared=req.is_shared,
    )
    db.add(view)
    await db.commit()
    await db.refresh(view)

    return SavedViewResponse(
        id=view.id,
        name=view.name,
        entity_type=view.entity_type,
        filters=view.filters or {},
        sort_config=view.sort_config or {},
        view_mode=view.view_mode or "list",
        group_by=view.group_by,
        is_default=view.is_default,
        is_shared=view.is_shared,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


@router.put(
    "/{view_id}",
    response_model=SavedViewResponse,
    summary="Update saved view",
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def update_saved_view(
    req: SavedViewUpdateRequest,
    org_id: UUID = Path(...),
    view_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Update a saved view. Only the owner can update."""
    result = await db.execute(
        select(SavedView).where(
            SavedView.id == view_id,
            SavedView.org_id == org_id,
        )
    )
    view = result.scalar_one_or_none()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")

    if view.member_id != member.id:
        raise HTTPException(status_code=403, detail="Can only update your own views")

    if req.name is not None:
        view.name = req.name
    if req.filters is not None:
        view.filters = req.filters
    if req.sort_config is not None:
        view.sort_config = req.sort_config
    if req.view_mode is not None:
        view.view_mode = req.view_mode
    if req.group_by is not None:
        view.group_by = req.group_by
    if req.is_default is not None:
        view.is_default = req.is_default
    if req.is_shared is not None:
        view.is_shared = req.is_shared

    await db.commit()
    await db.refresh(view)

    return SavedViewResponse(
        id=view.id,
        name=view.name,
        entity_type=view.entity_type,
        filters=view.filters or {},
        sort_config=view.sort_config or {},
        view_mode=view.view_mode or "list",
        group_by=view.group_by,
        is_default=view.is_default,
        is_shared=view.is_shared,
        created_at=view.created_at,
        updated_at=view.updated_at,
    )


@router.delete(
    "/{view_id}",
    status_code=204,
    summary="Delete saved view",
    responses={404: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def delete_saved_view(
    org_id: UUID = Path(...),
    view_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Delete a saved view. Only the owner can delete (unless shared)."""
    result = await db.execute(
        select(SavedView).where(
            SavedView.id == view_id,
            SavedView.org_id == org_id,
        )
    )
    view = result.scalar_one_or_none()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")

    # Allow deletion if owner, or if the view is shared and user is a member
    if view.member_id != member.id and not view.is_shared:
        raise HTTPException(status_code=403, detail="Can only delete your own views")

    await db.delete(view)
    await db.commit()
    return None
