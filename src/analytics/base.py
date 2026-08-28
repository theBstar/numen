"""Tracker abstract base - the provider-agnostic interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Tracker(ABC):
    """Analytics provider interface.

    Every `track` call should carry a `distinct_id` (the Numen member_id) and a
    properties dict. Implementations must never raise into caller code.
    """

    @abstractmethod
    async def identify(self, member_id: str, traits: dict[str, Any]) -> None: ...

    @abstractmethod
    async def group(self, org_id: str, traits: dict[str, Any]) -> None: ...

    @abstractmethod
    async def track(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None: ...

    @abstractmethod
    async def flush(self) -> None: ...

    @abstractmethod
    async def shutdown(self) -> None: ...
