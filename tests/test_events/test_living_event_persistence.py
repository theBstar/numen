"""Tests for the LivingEventPersistenceHandler.

Per the spike test plan: every Living event type must round-trip
through the bus and land in the ``living_event`` table; a DB write failure
must NOT abort the bus (preserve the existing handler contract).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.events.bus import EventBus
from src.events.handlers import (
    LivingEventPersistenceHandler,
    living_event_persistence_handler,
)
from src.events.types import (
    LIVING_EVENT_KINDS,
    LIVING_EVENT_TYPES,
    AgentInterventionEvent,
    ContextFetchEvent,
    SessionCompleteEvent,
    SessionStartEvent,
    WorktreeArchiveEvent,
    WorktreeSpawnEvent,
)


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def task_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000aaa")


@pytest.fixture
def agent_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000bbb")


@pytest.fixture
def worktree_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000ccc")


@pytest.fixture
def db():
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


def _ts():
    return datetime(2026, 5, 2, 19, 30, tzinfo=timezone.utc)


# ── basic shape ──────────────────────────────────────────────────────


def test_living_event_kinds_cover_every_type():
    """The kind map MUST have an entry for every event in the type tuple."""
    assert set(LIVING_EVENT_KINDS) == set(LIVING_EVENT_TYPES)
    # 6 subprocess-driven events + LivingTaskEvent (Lane B API ingest)
    # + 4 ship/merge events (PR/branch/merge tracking) = 11
    assert len(LIVING_EVENT_TYPES) == 11


def test_living_event_kind_strings_match_design_doc():
    expected = {
        ContextFetchEvent: "context_fetch",
        SessionStartEvent: "session_start",
        SessionCompleteEvent: "session_complete",
        WorktreeSpawnEvent: "worktree_spawn",
        WorktreeArchiveEvent: "worktree_archive",
        AgentInterventionEvent: "agent_intervention",
    }
    for klass, name in expected.items():
        assert LIVING_EVENT_KINDS[klass] == name


# ── round-trip: each event lands in the table ────────────────────────


def _events_under_test(db, org_id, task_id, agent_id, worktree_id):
    return [
        ContextFetchEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            task_query="implement passkey fallback",
            top_k_doc_ids=("doc-1", "doc-2"),
            total_tokens=1234,
            result_count=2,
            worktree_id=worktree_id,
        ),
        SessionStartEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            runtime="claude_code",
            worktree_id=worktree_id,
        ),
        SessionCompleteEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            runtime="claude_code",
            exit_code=0,
            duration_seconds=42.0,
            worktree_id=worktree_id,
            outcome="done",
        ),
        WorktreeSpawnEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            worktree_id=worktree_id,
            fs_path="/tmp/wt/abc",
            branch_name="agent/passkey",
        ),
        WorktreeArchiveEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            worktree_id=worktree_id,
            fs_path="/tmp/wt/abc",
            reason="ttl",
        ),
        AgentInterventionEvent(
            db=db,
            org_id=org_id,
            task_id=task_id,
            agent_id=agent_id,
            ts=_ts(),
            worktree_id=worktree_id,
            text="please use Postgres, not SQLite",
            direction="user_to_agent",
        ),
    ]


@pytest.mark.parametrize(
    "event_index", list(range(6)), ids=lambda i: LIVING_EVENT_KINDS[LIVING_EVENT_TYPES[i]]
)
async def test_each_event_type_round_trips_via_bus(
    event_index, db, org_id, task_id, agent_id, worktree_id
):
    """Every Living event subscribed to a fresh bus → handler writes one row."""
    bus = EventBus()
    handler = LivingEventPersistenceHandler()
    for klass in LIVING_EVENT_TYPES:
        bus.subscribe(klass, handler.handle, name=f"persist:{LIVING_EVENT_KINDS[klass]}")

    events = _events_under_test(db, org_id, task_id, agent_id, worktree_id)
    event = events[event_index]
    expected_kind = LIVING_EVENT_KINDS[type(event)]

    results = await bus.emit(event)

    # Bus reports success, no exception.
    assert results and results[0][1] is None
    # Exactly one INSERT into living_event.
    assert db.execute.await_count == 1
    args, _ = db.execute.await_args
    sql = str(args[0])
    params = args[1]
    assert "living_event" in sql
    assert params["org_id"] == org_id
    assert params["task_id"] == task_id
    assert params["agent_id"] == agent_id
    assert params["kind"] == expected_kind
    assert params["worktree_id"] == worktree_id
    # Payload is JSON-serializable and excludes the bus-internal fields.
    payload = json.loads(params["payload"])
    for excluded in ("db", "org_id", "task_id", "agent_id", "ts", "worktree_id"):
        assert excluded not in payload


async def test_payload_contains_event_specific_fields(db, org_id, task_id, agent_id, worktree_id):
    """ContextFetchEvent: top_k_doc_ids and tokens land in the payload."""
    handler = LivingEventPersistenceHandler()
    event = ContextFetchEvent(
        db=db,
        org_id=org_id,
        task_id=task_id,
        agent_id=agent_id,
        ts=_ts(),
        task_query="rebuild login",
        top_k_doc_ids=("a", "b", "c"),
        total_tokens=999,
        result_count=3,
        worktree_id=worktree_id,
    )

    await handler.handle(event)

    args, _ = db.execute.await_args
    payload = json.loads(args[1]["payload"])
    assert payload["task_query"] == "rebuild login"
    assert payload["top_k_doc_ids"] == ["a", "b", "c"]
    assert payload["total_tokens"] == 999
    assert payload["result_count"] == 3


# ── DB failure does not abort the bus ────────────────────────────────


async def test_db_write_failure_does_not_abort_bus(
    db, org_id, task_id, agent_id, worktree_id
):
    """If the persistence INSERT fails, the bus must still report the
    handler as successful (the handler swallows + logs the error)."""
    db.execute = AsyncMock(side_effect=RuntimeError("DB down"))

    bus = EventBus()
    handler = LivingEventPersistenceHandler()
    bus.subscribe(ContextFetchEvent, handler.handle, name="persist")

    other_called: list[str] = []

    async def downstream(event):
        other_called.append("ok")

    bus.subscribe(ContextFetchEvent, downstream, priority=200, name="downstream")

    event = ContextFetchEvent(
        db=db,
        org_id=org_id,
        task_id=task_id,
        agent_id=agent_id,
        ts=_ts(),
        task_query="x",
        worktree_id=worktree_id,
    )

    results = await bus.emit(event)

    # Persistence reported success (because handler swallowed the error)...
    assert results[0] == ("persist", None)
    # ...and the downstream handler still ran.
    assert other_called == ["ok"]


# ── replay: dump events for a task_id ────────────────────────────────


async def test_handler_writes_in_priority_order_per_task(
    db, org_id, task_id, agent_id, worktree_id
):
    """Emitting the full sequence of Living events for one task produces
    a row per event, all carrying the same task_id - which is the
    minimum requirement for the per-task-replay query in the design doc."""
    handler = LivingEventPersistenceHandler()
    seen_task_ids: list = []

    async def capture(stmt, params):
        seen_task_ids.append(params["task_id"])
        return MagicMock()

    db.execute = AsyncMock(side_effect=capture)

    for event in _events_under_test(db, org_id, task_id, agent_id, worktree_id):
        await handler.handle(event)

    assert len(seen_task_ids) == 6
    assert all(tid == task_id for tid in seen_task_ids)


# ── module-level singleton is wired ──────────────────────────────────


def test_module_singleton_is_a_handler_instance():
    assert isinstance(living_event_persistence_handler, LivingEventPersistenceHandler)


def test_register_all_subscribes_living_persistence_handlers():
    """register_all() must subscribe the persistence handler for every
    Living event type."""
    from src.events import handlers as handlers_mod

    # Use a brand-new bus to avoid polluting global state.
    bus_local = EventBus()
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(handlers_mod, "bus", bus_local)
        handlers_mod.register_all()

    for klass in LIVING_EVENT_TYPES:
        subs = bus_local._handlers.get(klass, [])
        assert any(
            f"living_event_persistence:{LIVING_EVENT_KINDS[klass]}" == name
            for _prio, name, _h in subs
        ), f"missing persistence handler subscription for {klass.__name__}"
