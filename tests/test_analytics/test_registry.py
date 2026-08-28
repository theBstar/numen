"""Tests for the tracker registry / provider resolution."""

from __future__ import annotations

import pytest

from src.analytics import registry
from src.analytics.console_provider import ConsoleTracker
from src.analytics.multi_provider import MultiTracker


@pytest.fixture(autouse=True)
def _reset_registry():
    registry.reset_tracker()
    yield
    registry.reset_tracker()


def test_defaults_to_console_when_unset(monkeypatch):
    monkeypatch.setattr(registry.settings, "analytics_providers", "")
    tracker = registry.get_tracker()
    assert isinstance(tracker, MultiTracker)
    assert len(tracker._providers) == 1
    assert isinstance(tracker._providers[0], ConsoleTracker)


def test_unknown_provider_is_ignored(monkeypatch):
    monkeypatch.setattr(registry.settings, "analytics_providers", "console,bogus")
    tracker = registry.get_tracker()
    assert isinstance(tracker, MultiTracker)
    assert len(tracker._providers) == 1
    assert isinstance(tracker._providers[0], ConsoleTracker)


def test_posthog_without_key_is_still_registered(monkeypatch):
    # The PostHog tracker itself no-ops when no key is set, but it should still
    # be registered so it's trivially replaced by setting env vars.
    monkeypatch.setattr(registry.settings, "analytics_providers", "posthog,console")
    monkeypatch.setattr(registry.settings, "posthog_api_key", "")
    tracker = registry.get_tracker()
    assert len(tracker._providers) == 2
