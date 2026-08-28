"""Email delivery for Numen daily briefings via Resend."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import resend
from sqlalchemy.ext.asyncio import AsyncSession

from src.briefing.slack_delivery import deliver_via_slack
from src.briefing.templates import render_briefing_email
from src.config import settings
from src.llm.actions import generate_briefing_narrative
from src.llm.provider import is_llm_configured
from src.shared.models import Briefing, OrgMember
from src.shared.types import BriefingItem, DeliveryStatus

logger = logging.getLogger(__name__)

# Configure Resend API key
resend.api_key = settings.resend_api_key

# Retry configuration
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 1.0


# ── Low-level email sending ─────────────────────────────────────────────


async def send_briefing_email(
    to_email: str,
    subject: str,
    html: str,
    text: str,
) -> bool:
    """Send an email via Resend with retry (3 attempts, exponential backoff).

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html: HTML body content.
        text: Plain-text body content.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            params: resend.Emails.SendParams = {
                "from": settings.briefing_from_email,
                "to": [to_email],
                "subject": subject,
                "html": html,
                "text": text,
            }

            # resend.Emails.send is synchronous; run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, resend.Emails.send, params)

            logger.info(
                "Briefing email sent to %s (attempt %d, id=%s)",
                to_email,
                attempt,
                response.get("id", "unknown") if isinstance(response, dict) else response,
            )
            return True

        except Exception:
            logger.warning(
                "Failed to send briefing email to %s (attempt %d/%d)",
                to_email,
                attempt,
                _MAX_RETRIES,
                exc_info=True,
            )
            if attempt < _MAX_RETRIES:
                backoff = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(backoff)

    logger.error(
        "All %d attempts to send briefing email to %s failed",
        _MAX_RETRIES,
        to_email,
    )
    return False


# ── DB record ────────────────────────────────────────────────────────────


async def record_briefing(
    db: AsyncSession,
    member_id: UUID,
    items: list[BriefingItem],
    status: DeliveryStatus,
    *,
    org_id: UUID,
    empty_reason: str | None = None,
    extra_content: dict | None = None,
) -> Briefing:
    """Create a Briefing DB record capturing the generated content and delivery status.

    Args:
        db: Async database session.
        member_id: The OrgMember ID who received (or was intended to receive) the briefing.
        items: The list of BriefingItems that were assembled.
        status: The delivery status (PENDING, SENT, FAILED).
        org_id: The organization ID for tenant scoping.
        empty_reason: Optional reason string when items is empty (e.g.
            "no_person_entity", "no_urgent_signals"). Persisted into content
            so the API can surface a useful empty state to the UI.
        extra_content: Optional extra keys to merge into the persisted content
            dict (e.g. ``channel``, ``slack_fallback``, ``fallback_reason``).

    Returns:
        The created Briefing ORM instance.
    """
    now = datetime.now(timezone.utc)

    content: dict = {
        "items": [item.model_dump(mode="json") for item in items],
        "item_count": len(items),
    }
    if empty_reason:
        content["empty_reason"] = empty_reason
    if extra_content:
        content.update(extra_content)

    briefing = Briefing(
        org_id=org_id,
        org_member_id=member_id,
        generated_at=now,
        content=content,
        delivered_at=now if status == DeliveryStatus.SENT else None,
        delivery_status=status,
    )

    db.add(briefing)
    await db.flush()

    logger.info(
        "Recorded briefing %s for member %s (status=%s, items=%d)",
        briefing.id,
        member_id,
        status.value,
        len(items),
    )

    return briefing


# ── High-level send ──────────────────────────────────────────────────────


async def send_briefing(
    db: AsyncSession,
    member: OrgMember,
    items: list[BriefingItem],
    *,
    empty_reason: str | None = None,
) -> bool:
    """Assemble, render, and deliver a briefing email to an org member.

    Steps:
        1. Optionally generate a narrative via Claude.
        2. Render HTML and plain-text email content.
        3. Send the email via Resend.
        4. Record the Briefing in the database.

    Args:
        db: Async database session.
        member: The OrgMember to send the briefing to.
        items: The assembled BriefingItems.
        empty_reason: Optional reason string when items is empty; stored on
            the Briefing record so the dashboard can render a meaningful
            empty state (e.g. "no_urgent_signals").

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    if not items:
        logger.info("No items for member %s (%s), skipping briefing", member.id, member.email)
        # Still record an empty briefing so the scheduler doesn't retry today
        # and the UI can surface the reason.
        await record_briefing(
            db,
            member.id,
            items,
            DeliveryStatus.PENDING,
            org_id=member.org_id,
            empty_reason=empty_reason,
        )
        await db.commit()
        return False

    display_name = member.display_name or member.email.split("@")[0]

    # 1. Generate narrative (best-effort; continue without it on failure)
    narrative: str | None = None
    try:
        if is_llm_configured(settings):
            result = await generate_briefing_narrative(
                items=items,
                role=member.role,
                person_name=display_name,
            )
            narrative = result.get("narrative") if isinstance(result, dict) else result
    except Exception:
        logger.warning(
            "Failed to generate narrative for member %s, continuing without it",
            member.id,
            exc_info=True,
        )

    # 2. Determine channel (default email)
    prefs = member.preferences or {}
    channel = prefs.get("briefing_channel", "email")
    extra_content: dict = {"channel": channel}

    # 3. Try Slack first if requested; record fallback metadata if it fails.
    if channel == "slack":
        slack_ok, fallback_reason = await deliver_via_slack(
            db, member, items, narrative=narrative
        )
        if slack_ok:
            await record_briefing(
                db,
                member.id,
                items,
                DeliveryStatus.SENT,
                org_id=member.org_id,
                extra_content=extra_content,
            )
            await db.commit()
            return True

        # Slack failed -- fall back to email and remember why.
        extra_content["channel"] = "email"
        extra_content["slack_fallback"] = True
        extra_content["fallback_reason"] = fallback_reason or "unknown"
        logger.info(
            "Slack delivery failed for member=%s (reason=%s); falling back to email",
            member.id,
            fallback_reason,
        )

    # 4. Render email content
    html, plain_text = render_briefing_email(
        member=member,
        items=items,
        narrative=narrative,
    )

    # 5. Send via Resend
    now = datetime.now(timezone.utc)
    subject = f"Your Numen Briefing -- {now.strftime('%b %-d, %Y')}"

    success = await send_briefing_email(
        to_email=member.email,
        subject=subject,
        html=html,
        text=plain_text,
    )

    # 6. Record in DB
    status = DeliveryStatus.SENT if success else DeliveryStatus.FAILED
    await record_briefing(
        db,
        member.id,
        items,
        status,
        org_id=member.org_id,
        extra_content=extra_content,
    )
    await db.commit()

    return success
