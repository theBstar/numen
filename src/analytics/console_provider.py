"""Console provider - logs events via stdlib logging. Default in dev/tests."""

from __future__ import annotations

import logging
from typing import Any

from src.analytics.base import Tracker

logger = logging.getLogger("numen.analytics")


class ConsoleTracker(Tracker):
    async def identify(self, member_id: str, traits: dict[str, Any]) -> None:
        logger.info("analytics.identify member_id=%s traits=%s", member_id, traits)

    async def group(self, org_id: str, traits: dict[str, Any]) -> None:
        logger.info("analytics.group org_id=%s traits=%s", org_id, traits)

    async def track(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        logger.info("analytics.track event=%s distinct_id=%s props=%s", event, distinct_id, properties or {})

    async def flush(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None
