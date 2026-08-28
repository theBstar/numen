"""Tests for analytics provider abstraction."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from src.analytics.base import Tracker
from src.analytics.console_provider import ConsoleTracker
from src.analytics.multi_provider import MultiTracker


class RecordingTracker(Tracker):
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def identify(self, member_id: str, traits: dict[str, Any]) -> None:
        self.calls.append(("identify", (member_id,), dict(traits)))

    async def group(self, org_id: str, traits: dict[str, Any]) -> None:
        self.calls.append(("group", (org_id,), dict(traits)))

    async def track(
        self,
        event: str,
        distinct_id: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append(("track", (event, distinct_id), dict(properties or {})))

    async def flush(self) -> None:
        self.calls.append(("flush", (), {}))

    async def shutdown(self) -> None:
        self.calls.append(("shutdown", (), {}))


class ExplodingTracker(Tracker):
    async def identify(self, member_id, traits): raise RuntimeError("boom")  # noqa: E701
    async def group(self, org_id, traits): raise RuntimeError("boom")  # noqa: E701
    async def track(self, event, distinct_id, properties=None): raise RuntimeError("boom")  # noqa: E701
    async def flush(self): raise RuntimeError("boom")  # noqa: E701
    async def shutdown(self): raise RuntimeError("boom")  # noqa: E701


@pytest.mark.asyncio
async def test_console_tracker_logs_events(caplog):
    caplog.set_level(logging.INFO, logger="numen.analytics")
    tracker = ConsoleTracker()
    await tracker.track("task.created", "member-1", {"task_id": "t-1", "org_id": "o-1"})
    assert any("analytics.track" in r.message and "task.created" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_multi_tracker_fans_out_to_all_providers():
    a, b = RecordingTracker(), RecordingTracker()
    multi = MultiTracker([a, b])
    await multi.track("task.created", "member-1", {"org_id": "o-1"})
    assert a.calls == [("track", ("task.created", "member-1"), {"org_id": "o-1"})]
    assert b.calls == a.calls


@pytest.mark.asyncio
async def test_multi_tracker_swallows_provider_errors():
    good = RecordingTracker()
    multi = MultiTracker([ExplodingTracker(), good])
    # Must not raise.
    await multi.track("task.created", "member-1", {"org_id": "o-1"})
    await multi.identify("member-1", {"role": "engineer"})
    await multi.group("o-1", {"name": "Acme"})
    await multi.flush()
    await multi.shutdown()
    assert len(good.calls) == 5


@pytest.mark.asyncio
async def test_multi_tracker_empty_providers_is_noop():
    multi = MultiTracker([])
    await multi.track("x", "y", {})  # must not raise
