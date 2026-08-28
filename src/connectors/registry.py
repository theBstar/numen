"""The single source of truth for which sources Numen can ingest.

Every caller that needs "give me the connector for X" resolves it here. Before
this module there were six hand-maintained maps - one factory in the sync
scheduler, four slug maps in the connectors route, one in the OAuth route - and
they had drifted: Jira was absent from the scheduler, so it never delta-synced
after the initial connect, and Notion and Google Docs were absent from the route
maps, so manual sync and webhooks for them returned 400 or were dropped.

Adding a connector means adding one entry here. ``tests/test_connectors/
test_registry.py`` fails if a connector is implemented but not registered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src.connectors.base import BaseConnector
from src.shared.types import SourceType


@dataclass(frozen=True)
class ConnectorSpec:
    """Everything the rest of the system needs to know about one source."""

    source: SourceType
    slug: str
    label: str
    factory: Callable[[], BaseConnector]
    supports_webhooks: bool = False


# ── Factories ─────────────────────────────────────────────────────────────
# Imports are deferred into the factory so that importing the registry does not
# drag in every connector's HTTP stack, and so a broken connector cannot take
# down startup for the others.


def _linear() -> BaseConnector:
    from src.connectors.linear import LinearConnector

    return LinearConnector()


def _github() -> BaseConnector:
    from src.connectors.github import GitHubConnector

    return GitHubConnector()


def _slack() -> BaseConnector:
    from src.connectors.slack import SlackConnector

    return SlackConnector()


def _jira() -> BaseConnector:
    from src.connectors.jira import JiraConnector

    return JiraConnector()


def _notion() -> BaseConnector:
    from src.connectors.notion import NotionConnector

    return NotionConnector()


def _gdocs() -> BaseConnector:
    from src.connectors.gdocs import GDocsConnector

    return GDocsConnector()


CONNECTORS: tuple[ConnectorSpec, ...] = (
    ConnectorSpec(SourceType.LINEAR, "linear", "Linear", _linear, supports_webhooks=True),
    ConnectorSpec(SourceType.GITHUB, "github", "GitHub", _github, supports_webhooks=True),
    ConnectorSpec(SourceType.SLACK, "slack", "Slack", _slack, supports_webhooks=True),
    ConnectorSpec(SourceType.JIRA, "jira", "Jira", _jira, supports_webhooks=True),
    ConnectorSpec(SourceType.NOTION, "notion", "Notion", _notion),
    ConnectorSpec(SourceType.GDOCS, "gdocs", "Google Docs", _gdocs),
)

_BY_SOURCE: dict[SourceType, ConnectorSpec] = {spec.source: spec for spec in CONNECTORS}
_BY_SLUG: dict[str, ConnectorSpec] = {spec.slug: spec for spec in CONNECTORS}

SUPPORTED_SOURCES: frozenset[SourceType] = frozenset(_BY_SOURCE)

# Connector instances are cached: they hold HTTP clients and rate-limit state
# that should live across sync cycles rather than being rebuilt every poll.
_instances: dict[SourceType, BaseConnector] = {}


def is_supported(source: SourceType) -> bool:
    """True if an implemented connector exists for *source*."""
    return source in _BY_SOURCE


def get_connector(source: SourceType) -> BaseConnector:
    """Return the singleton connector for *source*.

    Raises ``ValueError`` if the source has no implementation.
    """
    spec = _BY_SOURCE.get(source)
    if spec is None:
        raise ValueError(f"No connector implemented for source: {source.value}")

    cached = _instances.get(source)
    if cached is None:
        cached = spec.factory()
        _instances[source] = cached

    return cached


def spec_for_source(source: SourceType) -> ConnectorSpec | None:
    return _BY_SOURCE.get(source)


def spec_for_slug(slug: str) -> ConnectorSpec | None:
    """Resolve a URL path segment (``/connectors/github``) to its spec."""
    return _BY_SLUG.get(slug.lower())


def source_for_slug(slug: str) -> SourceType | None:
    spec = _BY_SLUG.get(slug.lower())
    return spec.source if spec else None


def connector_for_slug(slug: str) -> BaseConnector | None:
    """Resolve a slug straight to its connector, or None if unknown."""
    spec = _BY_SLUG.get(slug.lower())
    return get_connector(spec.source) if spec else None


def reset_cache() -> None:
    """Drop cached instances. For tests - production has no reason to call this."""
    _instances.clear()
