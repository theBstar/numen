"""Kanban WIP settings routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.schemas import (
    KanbanSettingItem,
    KanbanSettingsResponse,
    KanbanSettingsUpdateRequest,
)
from src.shared.models import KanbanSetting, Organization

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/kanban",
    tags=["kanban"],
    dependencies=[Depends(get_current_member)],
)


# ── Routes ────────────────────────────────────────────────────────────


@router.get(
    "/settings",
    response_model=KanbanSettingsResponse,
    summary="Get kanban settings",
)
async def get_kanban_settings(
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Get WIP limits for all kanban columns."""
    result = await db.execute(select(KanbanSetting).where(KanbanSetting.org_id == org_id))
    settings = result.scalars().all()

    items = [
        KanbanSettingItem(
            column_status=s.column_status,
            wip_limit=s.wip_limit,
        )
        for s in settings
    ]
    return KanbanSettingsResponse(items=items)


@router.put(
    "/settings",
    response_model=KanbanSettingsResponse,
    summary="Update kanban settings",
)
async def update_kanban_settings(
    req: KanbanSettingsUpdateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Upsert WIP limits for kanban columns."""
    for item in req.items:
        # Check if setting already exists
        result = await db.execute(
            select(KanbanSetting).where(
                KanbanSetting.org_id == org_id,
                KanbanSetting.column_status == item.column_status,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.wip_limit = item.wip_limit
        else:
            setting = KanbanSetting(
                org_id=org_id,
                column_status=item.column_status,
                wip_limit=item.wip_limit,
            )
            db.add(setting)

    await db.commit()

    # Return the updated settings
    result = await db.execute(select(KanbanSetting).where(KanbanSetting.org_id == org_id))
    all_settings = result.scalars().all()

    items = [
        KanbanSettingItem(
            column_status=s.column_status,
            wip_limit=s.wip_limit,
        )
        for s in all_settings
    ]
    return KanbanSettingsResponse(items=items)
