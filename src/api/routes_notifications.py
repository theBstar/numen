"""Notification routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    ErrorResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
)
from src.shared.models import Notification, OrgMember

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/notifications",
    tags=["notifications"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


def _notification_to_response(n: Notification) -> NotificationResponse:
    """Build a NotificationResponse from a Notification model."""
    return NotificationResponse(
        id=n.id,
        type=n.type,
        entity_id=n.entity_id,
        actor_id=n.actor_id,
        actor_name=None,
        title=n.title,
        details=n.details or {},
        read_at=n.read_at,
        created_at=n.created_at,
    )


# ── Routes ────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=NotificationListResponse,
    summary="List notifications",
)
async def list_notifications(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """List notifications for the current member (unread first, then by created_at desc)."""
    result = await db.execute(
        select(Notification)
        .where(
            Notification.org_id == org_id,
            Notification.member_id == member.id,
        )
        .order_by(
            # Unread first (NULL read_at sorts before non-NULL)
            Notification.read_at.asc().nulls_first(),
            Notification.created_at.desc(),
        )
    )
    notifications = result.scalars().all()

    items = [_notification_to_response(n) for n in notifications]
    return NotificationListResponse(items=items)


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark notification as read",
    responses={404: {"model": ErrorResponse}},
)
async def mark_as_read(
    org_id: UUID = Path(...),
    notification_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read."""
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.org_id == org_id,
            Notification.member_id == member.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    notification.read_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(notification)

    return _notification_to_response(notification)


@router.post(
    "/read-all",
    response_model=NotificationListResponse,
    summary="Mark all notifications as read",
)
async def mark_all_as_read(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Mark all unread notifications as read for the current member."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(Notification).where(
            Notification.org_id == org_id,
            Notification.member_id == member.id,
            Notification.read_at.is_(None),
        )
    )
    unread = result.scalars().all()

    for n in unread:
        n.read_at = now

    await db.commit()

    # Return updated list
    result = await db.execute(
        select(Notification)
        .where(
            Notification.org_id == org_id,
            Notification.member_id == member.id,
        )
        .order_by(Notification.created_at.desc())
    )
    all_notifications = result.scalars().all()

    items = [_notification_to_response(n) for n in all_notifications]
    return NotificationListResponse(items=items)


@router.get(
    "/unread-count",
    response_model=NotificationUnreadCountResponse,
    summary="Get unread notification count",
)
async def unread_count(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Get the count of unread notifications for the current member."""
    result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.org_id == org_id,
            Notification.member_id == member.id,
            Notification.read_at.is_(None),
        )
    )
    count = result.scalar() or 0

    return NotificationUnreadCountResponse(count=count)
