"""Multi-provider fan-out. Errors from one provider never affect the others."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.analytics.base import Tracker

logger = logging.getLogger(__name__)


class MultiTracker(Tracker):
    def __init__(self, providers: list[Tracker]) -> None:
        self._providers = providers

    async def _fanout(self, method: str, *args, **kwargs) -> None:
        if not self._providers:
            return
        results = await asyncio.gather(
            *(getattr(p, method)(*args, **kwargs) for p in self._providers),
            return_exceptions=True,
        )
        for provider, result in zip(self._providers, results, strict=True):
            if isinstance(result, Exception):
                logger.warning(
                    "Provider %s.%s raised %s",
                    type(provider).__name__,
                    method,
                    result,
                )

    async def identify(self, member_id: str, traits: dict[str, Any]) -> None:
        await self._fanout("identify", member_id, traits)

    async def group(self, org_id: str, traits: dict[str, Any]) -> None:
        await self._fanout("group", org_id, traits)

    async def track(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        await self._fanout("track", event, distinct_id, properties)

    async def flush(self) -> None:
        await self._fanout("flush")

    async def shutdown(self) -> None:
        await self._fanout("shutdown")
