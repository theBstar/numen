"""Briefing and activity feed routes."""

from __future__ import annotations

import logging
import time
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.events import track_briefing_generated
from src.api.dependencies import get_current_member, get_db
from src.api.rate_limit import limiter
from src.api.schemas import BriefingListResponse, BriefingResponse, TestBriefingResponse
from src.llm.provider import is_llm_configured
from src.shared.audit import log_action_safely
from src.shared.models import AuditLog, Briefing, OrgMember
from src.shared.types import BriefingItem, DeliveryStatus, EntityType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["briefings"])

# Audit-log actions that are infrastructure/system signals, not user-facing
# activity. Hidden from the /activity feed. Add a new string here to suppress
# it; writes still land in audit_logs unchanged.
_INTERNAL_ACTIVITY_EVENTS: frozenset[str] = frozenset(
    {
        "briefing.generated",
        "briefing.test_sent",
        "connector.synced",
        "connector.connected",
    }
)


@router.get("/orgs/{org_id}/briefings", response_model=BriefingListResponse)
async def list_briefings(
    org_id: UUID = Path(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    query = select(Briefing).where(Briefing.org_member_id == member.id).order_by(Briefing.generated_at.desc())
    total_result = await db.execute(
        select(func.count()).select_from(Briefing).where(Briefing.org_member_id == member.id)
    )
    total = total_result.scalar() or 0

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    briefings = result.scalars().all()

    items = []
    for b in briefings:
        items.append(
            BriefingResponse(
                id=b.id,
                org_member_id=b.org_member_id,
                generated_at=b.generated_at,
                items=b.content.get("items", []) if b.content else [],
                empty_reason=b.content.get("empty_reason") if b.content else None,
                delivery_status=b.delivery_status,
                delivered_at=b.delivered_at,
            )
        )

    return BriefingListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/orgs/{org_id}/briefings/latest", response_model=BriefingResponse | None)
async def get_latest_briefing(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Briefing).where(Briefing.org_member_id == member.id).order_by(Briefing.generated_at.desc()).limit(1)
    )
    briefing = result.scalar_one_or_none()
    if not briefing:
        return None

    return BriefingResponse(
        id=briefing.id,
        org_member_id=briefing.org_member_id,
        generated_at=briefing.generated_at,
        items=briefing.content.get("items", []) if briefing.content else [],
        empty_reason=briefing.content.get("empty_reason") if briefing.content else None,
        delivery_status=briefing.delivery_status,
        delivered_at=briefing.delivered_at,
    )


@router.post("/orgs/{org_id}/briefings/generate", response_model=BriefingResponse)
async def trigger_briefing(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Trigger an on-demand briefing for the current user. Recomputes urgency scores first."""
    try:
        from src.briefing.assembler import assemble_briefing
        from src.briefing.delivery import record_briefing
        from src.events import BriefingRequested, bus

        start = time.monotonic()

        # Emit event to trigger urgency scoring before assembly
        await bus.emit(BriefingRequested(db=db, org_id=org_id, member_id=member.id))

        items, empty_reason = await assemble_briefing(db, member)
        briefing = await record_briefing(
            db,
            member.id,
            items,
            DeliveryStatus.SENT,
            org_id=org_id,
            empty_reason=empty_reason,
        )
        await log_action_safely(
            db,
            org_id=org_id,
            user_id=member.user_id,
            action="briefing.generated",
            resource_type="briefing",
            resource_id=briefing.id,
            details={"item_count": len(items), "empty_reason": empty_reason},
        )
        await db.commit()

        await track_briefing_generated(
            member_id=str(member.id),
            org_id=str(org_id),
            briefing_id=str(briefing.id),
            item_count=len(items),
            generation_ms=int((time.monotonic() - start) * 1000),
            trigger="on_demand",
            source="api",
        )

        return BriefingResponse(
            id=briefing.id,
            org_member_id=briefing.org_member_id,
            generated_at=briefing.generated_at,
            items=briefing.content.get("items", []) if briefing.content else [],
            empty_reason=empty_reason,
            delivery_status=briefing.delivery_status,
            delivered_at=briefing.delivered_at,
        )
    except Exception as e:
        logger.error("Failed to generate briefing: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Briefing generation failed: {type(e).__name__}: {str(e)[:200]}",
        )


# ── Test delivery ─────────────────────────────────────────────────────


_SLACK_FAILURE_MESSAGES: dict[str, str] = {
    "no_token": "Slack is not connected for this workspace. Connect Slack first.",
    "missing_scopes": (
        "Slack token is missing chat:write/im:write -- "
        "reconnect Slack on the Connections page."
    ),
    "user_not_found": (
        "Slack couldn't find your email. Make sure your Slack profile email "
        "matches the email on your Numen account."
    ),
    "open_dm_failed": "Slack couldn't open a DM with you. Try reconnecting Slack.",
    "post_failed": "Slack rejected the message. Reconnecting Slack usually fixes this.",
}


@router.post("/orgs/{org_id}/briefings/test", response_model=TestBriefingResponse)
@limiter.limit("10/minute")
async def send_test_briefing(
    request: Request,
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Send a one-shot test briefing through the member's chosen channel.

    Unlike POST /briefings/generate this does NOT persist a Briefing row, so it
    won't gate the morning scheduler. Always returns 200 with delivered=true|false
    and a human-readable message describing the outcome.
    """
    from src.briefing.assembler import assemble_briefing
    from src.briefing.delivery import send_briefing_email
    from src.briefing.slack_delivery import deliver_via_slack
    from src.briefing.templates import render_briefing_email
    from src.config import settings as app_settings
    from src.llm.actions import generate_briefing_narrative

    prefs = member.preferences or {}
    channel = prefs.get("briefing_channel", "email")
    if channel not in ("email", "slack"):
        channel = "email"

    # Assemble the same items the scheduled briefing would carry. If empty,
    # fabricate one synthetic item so the user actually sees a message arrive.
    items, _empty_reason = await assemble_briefing(db, member)
    if not items:
        items = [
            BriefingItem(
                entity_id=uuid4(),
                entity_type=EntityType.TASK,
                title="Test briefing",
                why_it_matters=(
                    "This is a one-shot test from your Settings page. Your "
                    "dashboard has no urgent signals right now -- when it does, "
                    "they'll appear here in your scheduled briefing."
                ),
                urgency_score=0.5,
            )
        ]

    # Best-effort narrative (matches send_briefing).
    narrative: str | None = None
    try:
        if is_llm_configured(app_settings):
            display_name = member.display_name or member.email.split("@")[0]
            result = await generate_briefing_narrative(
                items=items, role=member.role, person_name=display_name
            )
            narrative = result.get("narrative") if isinstance(result, dict) else result
    except Exception:
        logger.warning("Test briefing: narrative generation failed", exc_info=True)

    delivered = False
    fallback_reason: str | None = None

    if channel == "slack":
        ok, reason = await deliver_via_slack(db, member, items, narrative=narrative)
        delivered = ok
        fallback_reason = reason
        if ok:
            message = "Sent to your Slack DM."
        else:
            message = _SLACK_FAILURE_MESSAGES.get(
                reason or "",
                f"Slack delivery failed ({reason or 'unknown'}).",
            )
    else:
        from datetime import datetime, timezone

        html, plain_text = render_briefing_email(member=member, items=items, narrative=narrative)
        subject = f"[Test] Your Numen Briefing -- {datetime.now(timezone.utc).strftime('%b %-d, %Y')}"
        delivered = await send_briefing_email(
            to_email=member.email, subject=subject, html=html, text=plain_text
        )
        fallback_reason = None if delivered else "email_send_failed"
        message = (
            f"Sent to {member.email}."
            if delivered
            else "Email send failed. Check Resend configuration."
        )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=member.user_id,
        action="briefing.test_sent",
        resource_type="briefing",
        details={
            "channel": channel,
            "delivered": delivered,
            "fallback_reason": fallback_reason,
            "item_count": len(items),
        },
    )
    await db.commit()

    return TestBriefingResponse(
        channel=channel,
        delivered=delivered,
        fallback_reason=fallback_reason,
        item_count=len(items),
        message=message,
    )


# ── Activity feed ─────────────────────────────────────────────────────


@router.get("/orgs/{org_id}/activity")
async def list_activity(
    org_id: UUID = Path(...),
    limit: int = Query(20, ge=1, le=100),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Return recent activity/audit log entries for the org."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.org_id == org_id)
        .where(~AuditLog.action.like("auth.%"))
        .where(AuditLog.action.notin_(_INTERNAL_ACTIVITY_EVENTS))
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
    )
    entries = result.scalars().all()
    return {
        "items": [
            {
                "id": str(e.id),
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": str(e.resource_id) if e.resource_id else None,
                "details": e.details,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ]
    }
