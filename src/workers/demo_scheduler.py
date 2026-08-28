"""Daily demo data variance scheduler. Runs at 8:30am UTC."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from src.config import settings
from src.shared.database import async_session
from src.shared.models import Organization

logger = logging.getLogger(__name__)


class DemoScheduler:
    """Applies daily variance to demo orgs so the data stays fresh.

    Checks every minute and triggers at 08:30 UTC. Uses the demo
    generator's seeded random so the same date always produces
    identical changes.
    """

    def __init__(self) -> None:
        self._running: bool = False
        self._last_run_date: str | None = None

    async def run(self) -> None:
        """Main loop - checks every minute for the trigger window.

        Returns immediately unless DEMO_MODE is on. Self-hosted installs have no
        demo org, so polling forever would be pure overhead.
        """
        if not settings.demo_mode:
            logger.info("DemoScheduler disabled (DEMO_MODE is off)")
            return

        self._running = True
        logger.info("DemoScheduler started")

        while self._running:
            try:
                now = datetime.now(timezone.utc)
                today = now.date().isoformat()

                # Trigger at 08:30 UTC, but only once per day
                if now.hour == 8 and 30 <= now.minute < 31 and self._last_run_date != today:
                    await self._apply_variance()
                    self._last_run_date = today

            except Exception as exc:
                logger.error("DemoScheduler check failed: %s", exc, exc_info=True)

            await asyncio.sleep(60)

    async def _apply_variance(self) -> None:
        """Find all demo orgs and apply daily variance."""
        logger.info("Applying daily demo data variance...")

        try:
            async with async_session() as db:
                result = await db.execute(select(Organization).where(Organization.is_demo.is_(True)))
                demo_orgs = list(result.scalars().all())

                if not demo_orgs:
                    logger.info("No demo orgs found - skipping variance")
                    return

                from src.demo.seeder import apply_daily_variance

                for org in demo_orgs:
                    try:
                        await apply_daily_variance(db, org.id)
                        logger.info(
                            "Daily variance applied for demo org: %s (%s)",
                            org.name,
                            org.id,
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to apply variance for org %s: %s",
                            org.id,
                            exc,
                            exc_info=True,
                        )

        except Exception as exc:
            logger.error("Failed to apply demo variance: %s", exc, exc_info=True)

    def stop(self) -> None:
        self._running = False
        logger.info("DemoScheduler stopped")


# Module-level singleton
demo_scheduler = DemoScheduler()
