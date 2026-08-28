"""Background worker that delivers daily briefings at each member's preferred local time."""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.database import async_session
from src.shared.models import Briefing, OrgMember
from src.shared.types import DeliveryStatus

logger = logging.getLogger(__name__)

# Default local hour (0-23) when a member has no `briefing_hour` preference set.
_DEFAULT_BRIEFING_LOCAL_HOUR = 8

# We consider a briefing "due" if the member's local time is within this
# window (in minutes) past the target hour.  This must be wider than the
# check interval (60 s) to avoid missed deliveries.
_BRIEFING_WINDOW_MINUTES = 10


class BriefingScheduler:
    """Checks every minute whether any org member is due for a daily briefing."""

    def __init__(self) -> None:
        self._running: bool = False

    # ── public interface ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop — checks every minute if it's time to send briefings."""
        self._running = True
        logger.info("Starting briefing scheduler")

        while self._running:
            try:
                await self._check_and_send()
            except Exception as exc:
                logger.error("Briefing check failed: %s", exc, exc_info=True)

            await asyncio.sleep(60)  # check every minute

    def stop(self) -> None:
        self._running = False
        logger.info("Briefing scheduler stopped")

    # ── internals ─────────────────────────────────────────────────────

    async def _check_and_send(self) -> None:
        """Iterate over all org members and send briefings to those who are due."""
        now = datetime.now(timezone.utc)

        async with async_session() as db:
            result = await db.execute(select(OrgMember))
            members: list[OrgMember] = list(result.scalars().all())

            for member in members:
                try:
                    if await self._is_briefing_due(db, member, now):
                        await self._send_briefing(db, member)
                except Exception as exc:
                    logger.error(
                        "Error processing briefing for member=%s: %s",
                        member.id,
                        exc,
                        exc_info=True,
                    )

            await db.commit()

    async def _is_briefing_due(
        self,
        db: AsyncSession,
        member: OrgMember,
        now: datetime,
    ) -> bool:
        """Return ``True`` if *member* should receive a briefing right now.

        The check has two parts:
        1. Is the member's local time within the briefing window (8:00-8:10)?
        2. Have they already received a briefing today (in their local tz)?
        """
        try:
            member_tz = ZoneInfo(member.timezone)
        except (KeyError, Exception):
            logger.warning(
                "Invalid timezone '%s' for member=%s — falling back to UTC",
                member.timezone,
                member.id,
            )
            member_tz = ZoneInfo("UTC")

        member_now = now.astimezone(member_tz)

        prefs = member.preferences or {}
        target_hour = prefs.get("briefing_hour", _DEFAULT_BRIEFING_LOCAL_HOUR)
        if not isinstance(target_hour, int) or not 0 <= target_hour <= 23:
            target_hour = _DEFAULT_BRIEFING_LOCAL_HOUR

        # Check if current local time falls within the briefing window.
        if member_now.hour != target_hour:
            return False
        if member_now.minute >= _BRIEFING_WINDOW_MINUTES:
            return False

        # Check if a briefing has already been sent today (member-local date).
        member_today: date = member_now.date()
        already_sent = await self._briefing_sent_today(db, member, member_today, member_tz)
        return not already_sent

    async def _briefing_sent_today(
        self,
        db: AsyncSession,
        member: OrgMember,
        member_today: date,
        member_tz: ZoneInfo,
    ) -> bool:
        """Return ``True`` if a briefing was already generated for *member* today."""
        # Compute the UTC range that corresponds to the member's local "today".
        local_start = datetime(
            member_today.year,
            member_today.month,
            member_today.day,
            tzinfo=member_tz,
        )
        local_end = datetime(
            member_today.year,
            member_today.month,
            member_today.day,
            23,
            59,
            59,
            tzinfo=member_tz,
        )
        utc_start = local_start.astimezone(timezone.utc)
        utc_end = local_end.astimezone(timezone.utc)

        result = await db.execute(
            select(Briefing.id)
            .where(
                Briefing.org_member_id == member.id,
                Briefing.generated_at >= utc_start,
                Briefing.generated_at <= utc_end,
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _send_briefing(self, db: AsyncSession, member: OrgMember) -> None:
        """Generate and deliver a briefing for *member*."""
        logger.info("Sending briefing to member=%s (org=%s)", member.id, member.org_id)

        try:
            from src.briefing.assembler import assemble_briefing
            from src.briefing.delivery import send_briefing

            items, empty_reason = await assemble_briefing(db, member)
            await send_briefing(db, member, items, empty_reason=empty_reason)
            logger.info("Briefing delivered to member=%s", member.id)

        except ImportError:
            # Briefing delivery module not yet implemented — create a
            # placeholder record so we don't retry within the same window.
            logger.warning(
                "Briefing delivery module not available; creating placeholder briefing for member=%s",
                member.id,
            )
            briefing = Briefing(
                org_id=member.org_id,
                org_member_id=member.id,
                content={"placeholder": True},
                delivery_status=DeliveryStatus.PENDING,
            )
            db.add(briefing)
            await db.flush()

        except Exception as exc:
            logger.error(
                "Failed to deliver briefing to member=%s: %s",
                member.id,
                exc,
                exc_info=True,
            )
            # Record the failed attempt so we don't retry endlessly.
            briefing = Briefing(
                org_id=member.org_id,
                org_member_id=member.id,
                content={"error": str(exc)[:1000]},
                delivery_status=DeliveryStatus.FAILED,
            )
            db.add(briefing)
            await db.flush()


# Module-level singleton
briefing_scheduler = BriefingScheduler()
