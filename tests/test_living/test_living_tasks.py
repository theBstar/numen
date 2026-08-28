"""Tests for /api/living/tasks endpoints (Lane B)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.living import tasks_router
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.shared.types import AgentRuntime, LivingTaskStatus

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")


def _row_for(task):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=task)
    return res


def _list_row(items, total=None):
    res = MagicMock()
    res.scalars = MagicMock(
        return_value=MagicMock(all=MagicMock(return_value=items))
    )
    res.scalar = MagicMock(return_value=total if total is not None else len(items))
    return res


def _make_task(
    org_id=ORG_A, status=LivingTaskStatus.QUEUED, runtime=AgentRuntime.CLAUDE_CODE
):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.org_id = org_id
    t.name = "Test task"
    t.description = None
    t.runtime = runtime
    t.status = status
    t.worktree_id = None
    t.created_at = datetime.now(timezone.utc)
    t.started_at = None
    t.completed_at = None
    t.context_fetch_count = 0
    t.error_msg = None
    return t


def _build_app(principal_org=ORG_A, db_factory=None):
    app = FastAPI()
    app.include_router(tasks_router)

    async def override_db():
        if db_factory is None:
            db = AsyncMock()
            db.execute = AsyncMock()
            db.flush = AsyncMock()
            db.commit = AsyncMock()
            db.add = MagicMock()
            yield db
        else:
            yield db_factory()

    async def override_principal():
        return LivingPrincipal(org_id=principal_org, user_id=USER_ID, via_api_key=True)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_living_principal] = override_principal
    return app


# ── Create ───────────────────────────────────────────────────────────


def test_create_task_201():
    captured = {}

    def make_db():
        db = AsyncMock()
        db.execute = AsyncMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()

        def _add(obj):
            # Simulate DB defaults
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
            obj.context_fetch_count = 0
            obj.worktree_id = None
            obj.started_at = None
            obj.completed_at = None
            obj.error_msg = None
            captured["task"] = obj

        db.add = MagicMock(side_effect=_add)
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.post(
            "/api/living/tasks",
            json={"name": "ship the spike", "runtime": "claude_code"},
        )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "ship the spike"
    assert body["runtime"] == "claude_code"
    assert body["status"] == "queued"
    assert body["org_id"] == str(ORG_A)


# ── List (paginated contract) ────────────────────────────────────────


def test_list_tasks_paginated():
    items = [_make_task() for _ in range(3)]

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_list_row([], total=3), _list_row(items)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.get("/api/living/tasks?page=1&page_size=10")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {"items", "total", "page", "page_size"}
    assert body["total"] == 3
    assert body["page"] == 1
    assert body["page_size"] == 10
    assert len(body["items"]) == 3


# ── Get single (cross-org isolation) ─────────────────────────────────


def test_get_task_404_when_other_org():
    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        # Query is scoped by org_id; a foreign org task is filtered out -> None
        db.execute = AsyncMock(return_value=_row_for(None))
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.get(f"/api/living/tasks/{uuid.uuid4()}")
    assert r.status_code == 404
    assert "detail" in r.json()


def test_get_task_happy_path():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=_row_for(task))
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.get(f"/api/living/tasks/{task.id}")
    assert r.status_code == 200
    assert r.json()["id"] == str(task.id)


# ── State-machine: every transition + invalid transitions ────────────


@pytest.mark.parametrize(
    "current,target,ok",
    [
        # Happy path
        (LivingTaskStatus.QUEUED, LivingTaskStatus.SPAWNING, True),
        (LivingTaskStatus.SPAWNING, LivingTaskStatus.RUNNING, True),
        (LivingTaskStatus.RUNNING, LivingTaskStatus.DONE, True),
        (LivingTaskStatus.SPAWNING, LivingTaskStatus.FAILED, True),
        (LivingTaskStatus.RUNNING, LivingTaskStatus.FAILED, True),
        (LivingTaskStatus.QUEUED, LivingTaskStatus.CANCELLED, True),
        (LivingTaskStatus.RUNNING, LivingTaskStatus.CANCELLED, True),
        # Illegal: skip ahead
        (LivingTaskStatus.QUEUED, LivingTaskStatus.RUNNING, False),
        (LivingTaskStatus.QUEUED, LivingTaskStatus.DONE, False),
        # Illegal: backward
        (LivingTaskStatus.RUNNING, LivingTaskStatus.QUEUED, False),
        (LivingTaskStatus.DONE, LivingTaskStatus.RUNNING, False),
        # Illegal: terminal -> anything
        (LivingTaskStatus.CANCELLED, LivingTaskStatus.RUNNING, False),
        (LivingTaskStatus.FAILED, LivingTaskStatus.RUNNING, False),
        # Illegal: spawning -> cancelled (per state machine)
        (LivingTaskStatus.SPAWNING, LivingTaskStatus.CANCELLED, False),
    ],
)
def test_status_transitions(current, target, ok):
    task = _make_task(status=current)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=_row_for(task))
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.patch(
            f"/api/living/tasks/{task.id}/status",
            json={"status": target.value},
        )
    if ok:
        assert r.status_code == 200, r.text
        assert r.json()["status"] == target.value
    else:
        assert r.status_code == 409, r.text
        assert "detail" in r.json()


def test_status_patch_404_cross_org():
    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        return db

    app = _build_app(db_factory=make_db)
    with TestClient(app) as c:
        r = c.patch(
            f"/api/living/tasks/{uuid.uuid4()}/status",
            json={"status": "spawning"},
        )
    assert r.status_code == 404


# ── Auth required ────────────────────────────────────────────────────


def test_endpoints_require_auth():
    """Without overriding the principal, the real auth dep runs and 401s."""
    app = FastAPI()
    app.include_router(tasks_router)

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        yield db

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as c:
        for url, method in [
            ("/api/living/tasks", "GET"),
            ("/api/living/tasks", "POST"),
            (f"/api/living/tasks/{uuid.uuid4()}", "GET"),
            (f"/api/living/tasks/{uuid.uuid4()}/status", "PATCH"),
        ]:
            r = c.request(method, url, json={"name": "x", "runtime": "claude_code"})
            assert r.status_code == 401, f"{method} {url}: {r.status_code}"
