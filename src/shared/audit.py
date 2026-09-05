"""Audit logging helper."""

import asyncio
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import AuditLog

logger = logging.getLogger(__name__)


async def log_action(
    db: AsyncSession,
    *,
    org_id: UUID | None = None,
    user_id: UUID | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    entry = AuditLog(
        org_id=org_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()


async def log_action_safely(
    db: AsyncSession,
    *,
    org_id: UUID | None = None,
    user_id: UUID | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: UUID | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    """Fire-and-forget audit log. A failed write never 500s the user action.

    The insert runs inside a SAVEPOINT. Swallowing the exception is not enough
    on its own: a failed flush leaves the session in SQLAlchemy's
    pending-rollback state, so the caller's next statement raises
    PendingRollbackError and the request 500s anyway - which is exactly what
    this function exists to prevent. The savepoint confines the failure so the
    surrounding transaction survives.

    Still propagates CancelledError so task cancellation works.
    """
    try:
        async with db.begin_nested():
            await log_action(
                db,
                org_id=org_id,
                user_id=user_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details,
                ip_address=ip_address,
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(
            "audit log write failed (action=%s): %s", action, exc, exc_info=False
        )
