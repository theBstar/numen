"""The connector registry is the single source of truth for which sources sync.

Numen previously carried two hand-written connector factories - one in the sync
scheduler, one in the connectors API route - and they drifted. Jira was missing
from the scheduler (so it never delta-synced after the initial connect) and
Notion and Google Docs were missing from the route (so manual sync returned
400). The drift test below is the point of this file: it fails the moment a
connector is implemented but not registered.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pytest

import src.connectors as connectors_pkg
from src.connectors.base import BaseConnector
from src.connectors.registry import (
    SUPPORTED_SOURCES,
    get_connector,
    is_supported,
)
from src.shared.types import SourceType


def _implemented_connector_classes() -> list[type[BaseConnector]]:
    """Discover every concrete BaseConnector subclass under src/connectors/."""
    found: list[type[BaseConnector]] = []

    for module_info in pkgutil.iter_modules(connectors_pkg.__path__):
        if module_info.name.startswith("_") or module_info.name in {"base", "registry"}:
            continue

        module = importlib.import_module(f"src.connectors.{module_info.name}")

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                issubclass(obj, BaseConnector)
                and obj is not BaseConnector
                and not inspect.isabstract(obj)
                and obj.__module__ == module.__name__
            ):
                found.append(obj)

    return found


def test_every_implemented_connector_is_registered():
    """A connector that exists but is not registered silently never syncs."""
    implemented = _implemented_connector_classes()
    assert implemented, "connector discovery found nothing - the walk is broken"

    missing = [cls.__name__ for cls in implemented if cls.source not in SUPPORTED_SOURCES]

    assert not missing, (
        f"These connectors are implemented but absent from the registry, so they "
        f"will never sync: {missing}. Add them to src/connectors/registry.py."
    )


def test_jira_is_registered():
    """Regression: Jira shipped fully wired through OAuth but never delta-synced."""
    assert SourceType.JIRA in SUPPORTED_SOURCES
    assert get_connector(SourceType.JIRA).source is SourceType.JIRA


@pytest.mark.parametrize("source", sorted(SUPPORTED_SOURCES, key=lambda s: s.value))
def test_registered_connector_reports_its_own_source(source: SourceType):
    """The registry key and the connector's declared source must agree."""
    assert get_connector(source).source is source


@pytest.mark.parametrize("source", sorted(SUPPORTED_SOURCES, key=lambda s: s.value))
def test_registered_connector_implements_the_interface(source: SourceType):
    connector = get_connector(source)
    assert isinstance(connector, BaseConnector)
    assert not inspect.isabstract(type(connector))


def test_get_connector_is_cached():
    """Connectors hold HTTP clients - building a new one per sync cycle is waste."""
    assert get_connector(SourceType.GITHUB) is get_connector(SourceType.GITHUB)


def test_unsupported_source_raises():
    with pytest.raises(ValueError, match="datadog"):
        get_connector(SourceType.DATADOG)


def test_is_supported_matches_get_connector():
    """is_supported must never disagree with what get_connector actually does."""
    for source in SourceType:
        if is_supported(source):
            assert get_connector(source) is not None
        else:
            with pytest.raises(ValueError):
                get_connector(source)


def test_manual_source_is_not_syncable():
    """MANUAL entities are created in-product; there is nothing to sync from."""
    assert not is_supported(SourceType.MANUAL)
