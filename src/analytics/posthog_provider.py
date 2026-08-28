"""PostHog provider. No-op if the SDK is missing or the API key is absent."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.analytics.base import Tracker

logger = logging.getLogger(__name__)


class PostHogTracker(Tracker):
    def __init__(self, api_key: str, host: str) -> None:
        self._enabled = False
        self._client = None
        if not api_key:
            logger.info("PostHog disabled (no POSTHOG_API_KEY set)")
            return
        try:
            from posthog import Posthog

            self._client = Posthog(project_api_key=api_key, host=host)
            self._enabled = True
        except ImportError:
            logger.warning("posthog package not installed; PostHog tracker disabled")

    async def _run(self, fn, *args, **kwargs) -> None:
        if not self._enabled or self._client is None:
            return
        try:
            await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            logger.warning("PostHog call failed: %s", e)

    async def identify(self, member_id: str, traits: dict[str, Any]) -> None:
        if not self._enabled or self._client is None:
            return
        await self._run(self._client.identify, member_id, traits)

    async def group(self, org_id: str, traits: dict[str, Any]) -> None:
        if not self._enabled or self._client is None:
            return
        await self._run(self._client.group_identify, "organization", org_id, traits)

    async def track(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        if not self._enabled or self._client is None:
            return
        props = dict(properties or {})
        org_id = props.get("org_id")
        groups = {"organization": org_id} if org_id else None
        await self._run(
            self._client.capture,
            distinct_id=distinct_id,
            event=event,
            properties=props,
            groups=groups,
        )

    async def flush(self) -> None:
        if not self._enabled or self._client is None:
            return
        await self._run(self._client.flush)

    async def shutdown(self) -> None:
        if not self._enabled or self._client is None:
            return
        await self._run(self._client.shutdown)
