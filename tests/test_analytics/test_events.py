"""Tests for the event catalog + typed helpers."""

from __future__ import annotations

from typing import Any

import pytest

from src.analytics import registry
from src.analytics.base import Tracker
from src.analytics.events import (
    Events,
    track_briefing_generated,
    track_connector_connected,
    track_task_created,
    track_task_status_changed,
)


class CapturingTracker(Tracker):
    def __init__(self) -> None:
        self.tracks: list[tuple[str, str, dict[str, Any]]] = []

    async def identify(self, member_id, traits): ...
    async def group(self, org_id, traits): ...

    async def track(self, event, distinct_id, properties=None):
        self.tracks.append((event, distinct_id, dict(properties or {})))

    async def flush(self): ...
    async def shutdown(self): ...


@pytest.fixture
def capturing_tracker(monkeypatch):
    tracker = CapturingTracker()
    registry._tracker = tracker
    yield tracker
    registry.reset_tracker()


def test_event_names_are_stable():
    # Guard against accidental renames of shipped event names.
    assert Events.TASK_CREATED == "task.created"
    assert Events.TASK_STATUS_CHANGED == "task.status_changed"
    assert Events.BRIEFING_GENERATED == "briefing.generated"
    assert Events.CONNECTOR_CONNECTED == "connector.connected"


@pytest.mark.asyncio
async def test_track_task_created_emits_reserved_props(capturing_tracker):
    await track_task_created(
        member_id="m-1",
        org_id="o-1",
        task_id="t-1",
        origin="manual",
        project_id="p-1",
    )
    assert len(capturing_tracker.tracks) == 1
    event, distinct_id, props = capturing_tracker.tracks[0]
    assert event == "task.created"
    assert distinct_id == "m-1"
    assert props["org_id"] == "o-1"
    assert props["task_id"] == "t-1"
    assert props["origin"] == "manual"
    assert props["project_id"] == "p-1"
    assert "environment" in props
    assert props["source"] == "api"


@pytest.mark.asyncio
async def test_track_task_status_changed(capturing_tracker):
    await track_task_status_changed(
        member_id="m-1",
        org_id="o-1",
        task_id="t-1",
        from_status="todo",
        to_status="in_progress",
    )
    event, _, props = capturing_tracker.tracks[0]
    assert event == "task.status_changed"
    assert props["from_status"] == "todo"
    assert props["to_status"] == "in_progress"


@pytest.mark.asyncio
async def test_track_briefing_generated(capturing_tracker):
    await track_briefing_generated(
        member_id="m-1",
        org_id="o-1",
        briefing_id="b-1",
        item_count=5,
        generation_ms=123,
        trigger="on_demand",
        source="api",
    )
    event, _, props = capturing_tracker.tracks[0]
    assert event == "briefing.generated"
    assert props["item_count"] == 5
    assert props["trigger"] == "on_demand"
    assert props["source"] == "api"


@pytest.mark.asyncio
async def test_track_connector_connected(capturing_tracker):
    await track_connector_connected(
        member_id="system",
        org_id="o-1",
        connector="linear",
        scopes=["read", "write"],
    )
    event, _, props = capturing_tracker.tracks[0]
    assert event == "connector.connected"
    assert props["connector"] == "linear"
    assert props["scopes"] == ["read", "write"]


@pytest.mark.asyncio
async def test_empty_distinct_id_is_skipped(capturing_tracker):
    await track_task_created(
        member_id="",
        org_id="o-1",
        task_id="t-1",
    )
    assert capturing_tracker.tracks == []


@pytest.mark.asyncio
async def test_tracker_exceptions_are_swallowed(monkeypatch):
    class Broken(Tracker):
        async def identify(self, *a, **k): raise RuntimeError("x")  # noqa: E701
        async def group(self, *a, **k): raise RuntimeError("x")  # noqa: E701
        async def track(self, *a, **k): raise RuntimeError("x")  # noqa: E701
        async def flush(self): raise RuntimeError("x")  # noqa: E701
        async def shutdown(self): raise RuntimeError("x")  # noqa: E701

    registry._tracker = Broken()
    try:
        # Must not raise.
        await track_task_created(member_id="m-1", org_id="o-1", task_id="t-1")
    finally:
        registry.reset_tracker()
