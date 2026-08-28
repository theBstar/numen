"""Tests for /api/living/tasks/{id}/events ingest."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.living import events_router
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.shared.types import AgentRuntime, LivingTaskStatus

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")


def _row_for(task):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=task)
    return res


def _make_task(org_id=ORG_A):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.org_id = org_id
    t.runtime = AgentRuntime.CLAUDE_CODE
    t.status = LivingTaskStatus.RUNNING
    t.context_fetch_count = 0
    t.created_at = datetime.now(timezone.utc)
    return t


def _build_app(task, principal_org=ORG_A):
    app = FastAPI()
    app.include_router(events_router)

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(task))
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        yield db

    async def override_principal():
        return LivingPrincipal(org_id=principal_org, user_id=USER_ID, via_api_key=True)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_living_principal] = override_principal
    return app


def test_ingest_valid_event_emits_and_acks():
    task = _make_task()
    app = _build_app(task)
    with patch("src.api.living.events.bus.emit", new=AsyncMock(return_value=[("h", None)])):
        with TestClient(app) as c:
            r = c.post(
                f"/api/living/tasks/{task.id}/events",
                json={
                    "kind": "session_start",
                    "payload": {"foo": "bar"},
                    "agent_id": str(uuid.uuid4()),
                },
            )
    assert r.status_code == 202, r.text
    assert r.json()["ok"] is True
    assert r.json()["handlers_invoked"] == 1


def test_ingest_invalid_kind_400():
    task = _make_task()
    app = _build_app(task)
    with TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/events",
            json={"kind": "not_a_kind", "payload": {}},
        )
    assert r.status_code == 400
    assert "Allowed" in r.json()["detail"]


def test_ingest_404_when_task_belongs_to_other_org():
    """task.org_id != principal.org_id (the SQL filter would already drop it
    before returning a row, so the route sees None -> 404)."""
    app = _build_app(task=None)
    with TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{uuid.uuid4()}/events",
            json={"kind": "session_start", "payload": {}},
        )
    assert r.status_code == 404


def test_ingest_context_fetch_bumps_counter():
    task = _make_task()
    app = _build_app(task)
    with patch("src.api.living.events.bus.emit", new=AsyncMock(return_value=[])):
        with TestClient(app) as c:
            r = c.post(
                f"/api/living/tasks/{task.id}/events",
                json={"kind": "context_fetch", "payload": {}},
            )
    assert r.status_code == 202
    assert task.context_fetch_count == 1


def test_ingest_requires_auth():
    app = FastAPI()
    app.include_router(events_router)

    async def override_db():
        db = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{uuid.uuid4()}/events",
            json={"kind": "session_start", "payload": {}},
        )
    assert r.status_code == 401
