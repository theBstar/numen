"""Platform-agnostic analytics tracking.

All call sites import from `src.analytics.events` (typed helpers) or the
module-level `tracker` from `src.analytics.registry`. Providers are swappable
via the `ANALYTICS_PROVIDERS` env var.
"""

from src.analytics.base import Tracker
from src.analytics.registry import get_tracker

__all__ = ["Tracker", "get_tracker"]
