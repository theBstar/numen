"""Lightweight in-process event bus (Observer/Pub-Sub pattern)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")
Handler = Callable[[T], Coroutine[Any, Any, None]]


class EventBus:
    """Synchronous in-process event bus.

    Handlers run in the same async call stack as the emitter, sharing the
    same database transaction. Errors are logged and continued - a failing
    handler never aborts the emitter or other handlers.
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[tuple[int, str, Handler]]] = defaultdict(list)

    def subscribe(
        self,
        event_type: type[T],
        handler: Handler[T],
        *,
        priority: int = 100,
        name: str | None = None,
    ) -> None:
        """Register a handler. Lower priority numbers run first."""
        handler_name = name or handler.__qualname__
        self._handlers[event_type].append((priority, handler_name, handler))
        self._handlers[event_type].sort(key=lambda t: t[0])

    async def emit(self, event: T) -> list[tuple[str, Exception | None]]:
        """Dispatch event to all subscribed handlers in priority order.

        Returns list of (handler_name, error_or_none) for observability.
        """
        event_type = type(event)
        handlers = self._handlers.get(event_type, [])
        results: list[tuple[str, Exception | None]] = []

        for _priority, handler_name, handler in handlers:
            try:
                await handler(event)
                results.append((handler_name, None))
            except Exception as exc:
                logger.warning(
                    "Handler %s failed for %s: %s",
                    handler_name,
                    event_type.__name__,
                    exc,
                    exc_info=True,
                )
                results.append((handler_name, exc))

        if results:
            ok = sum(1 for _, err in results if err is None)
            failed = len(results) - ok
            logger.debug(
                "event=%s handlers_ok=%d handlers_failed=%d",
                event_type.__name__,
                ok,
                failed,
            )

        return results


# Module-level singleton used throughout the app
bus = EventBus()
