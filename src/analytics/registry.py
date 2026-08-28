"""Tracker singleton. Built lazily from `settings.analytics_providers`."""

from __future__ import annotations

import logging

from src.analytics.base import Tracker
from src.analytics.console_provider import ConsoleTracker
from src.analytics.multi_provider import MultiTracker
from src.analytics.posthog_provider import PostHogTracker
from src.config import settings

logger = logging.getLogger(__name__)

_tracker: Tracker | None = None


def _build_tracker() -> Tracker:
    names = [n.strip().lower() for n in settings.analytics_providers.split(",") if n.strip()]
    providers: list[Tracker] = []
    for name in names:
        if name == "console":
            providers.append(ConsoleTracker())
        elif name == "posthog":
            providers.append(PostHogTracker(settings.posthog_api_key, settings.posthog_host))
        else:
            logger.warning("Unknown analytics provider '%s' (ignored)", name)
    if not providers:
        providers.append(ConsoleTracker())
    return MultiTracker(providers)


def get_tracker() -> Tracker:
    global _tracker
    if _tracker is None:
        _tracker = _build_tracker()
    return _tracker


def reset_tracker() -> None:
    """Test-only: drops the cached tracker so the next get_tracker() rebuilds."""
    global _tracker
    _tracker = None
