"""Tests for /api/living/tasks/{id}/pull-request + /merge endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.living import pull_requests_router
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.shared.types import (
    AgentRuntime,
    LivingMergeStateStatus,
    LivingPrProvider,
    LivingPrState,
    LivingTaskStatus,
)

ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000b2")
USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")


# ── Helpers ──────────────────────────────────────────────────────────


def _row_for(obj):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=obj)
    return res


def _make_task(org_id=ORG_A, status=LivingTaskStatus.RUNNING):
    t = MagicMock()
    t.id = uuid.uuid4()
    t.org_id = org_id
    t.name = "Test task"
    t.description = None
    t.runtime = AgentRuntime.CLAUDE_CODE
    t.status = status
    t.worktree_id = None
    t.created_at = datetime.now(timezone.utc)
    t.started_at = datetime.now(timezone.utc)
    t.completed_at = None
    t.context_fetch_count = 0
    t.error_msg = None
    return t


def _make_pr(
    task_id,
    org_id=ORG_A,
    pr_state=LivingPrState.OPEN,
    merge_state_status=LivingMergeStateStatus.UNKNOWN,
    provider=LivingPrProvider.GITHUB,
    pr_number=42,
):
    pr = MagicMock()
    pr.id = uuid.uuid4()
    pr.task_id = task_id
    pr.org_id = org_id
    pr.branch_name = "feat/test"
    pr.base_branch = "main"
    pr.commit_head_sha = "abc1234"
    pr.provider = provider
    pr.pr_number = pr_number
    pr.pr_url = f"https://github.com/owner/repo/pull/{pr_number}" if pr_number else None
    pr.pr_state = pr_state
    pr.merge_state_status = merge_state_status
    pr.merge_strategy = None
    pr.created_at = datetime.now(timezone.utc)
    pr.updated_at = datetime.now(timezone.utc)
    pr.merged_at = None
    return pr


def _init_pr_defaults(obj):
    """Simulate DB defaults so the upsert response can serialize."""
    obj.id = uuid.uuid4()
    obj.created_at = datetime.now(timezone.utc)
    obj.updated_at = datetime.now(timezone.utc)
    obj.merged_at = None
    obj.merge_state_status = LivingMergeStateStatus.UNKNOWN
    obj.merge_strategy = None


def _build_app(db_factory, principal_org=ORG_A):
    app = FastAPI()
    app.include_router(pull_requests_router)

    async def override_db():
        yield db_factory()

    async def override_principal():
        return LivingPrincipal(org_id=principal_org, user_id=USER_ID, via_api_key=True)

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_living_principal] = override_principal
    return app


# Each test patches bus.emit so the persistence handler doesn't try to write
# to a real DB. Returns the mock so tests can assert on emitted events.
def _patch_bus():
    return patch("src.services.pr_lifecycle.bus.emit", new=AsyncMock(return_value=[]))


# ── branch-pushed ────────────────────────────────────────────────────


def test_branch_pushed_204_emits_event():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        db.execute = AsyncMock(return_value=_row_for(task))
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/branch-pushed",
            json={"branch_name": "feat/test", "commit_sha": "abc1234"},
        )
    assert r.status_code == 204, r.text
    assert emit.await_count == 1
    event = emit.await_args.args[0]
    assert event.branch_name == "feat/test"
    assert event.commit_sha == "abc1234"
    assert event.task_id == task.id


def test_branch_pushed_404_cross_org():
    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        return db

    app = _build_app(make_db)
    with _patch_bus(), TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{uuid.uuid4()}/branch-pushed",
            json={"branch_name": "feat/x", "commit_sha": "deadbee"},
        )
    assert r.status_code == 404


# ── pull-request POST (upsert) ───────────────────────────────────────


def test_upsert_pr_creates_when_missing():
    task = _make_task()
    captured = {}

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        # 1st execute: load task. 2nd execute: load PR (returns None).
        responses = [_row_for(task), _row_for(None)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)

        def _add(obj):
            obj.id = uuid.uuid4()
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = datetime.now(timezone.utc)
            obj.merged_at = None
            obj.merge_state_status = LivingMergeStateStatus.UNKNOWN
            obj.merge_strategy = None
            captured["pr"] = obj

        db.add = MagicMock(side_effect=_add)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/pull-request",
            json={
                "branch_name": "feat/ship-tab",
                "base_branch": "main",
                "provider": "github",
                "pr_number": 17,
                "pr_url": "https://github.com/owner/repo/pull/17",
                "commit_head_sha": "deadbee",
                "draft": False,
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["branch_name"] == "feat/ship-tab"
    assert body["pr_state"] == "open"
    assert body["provider"] == "github"
    # Created => state changed from N/A to open => one event.
    assert emit.await_count == 1
    assert emit.await_args.args[0].pr_state == "open"


def test_upsert_pr_draft_starts_draft_state():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        responses = [_row_for(task), _row_for(None)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        db.add = MagicMock(side_effect=_init_pr_defaults)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/pull-request",
            json={
                "branch_name": "feat/x",
                "base_branch": "main",
                "provider": "github",
                "draft": True,
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["pr_state"] == "draft"
    assert emit.await_args.args[0].pr_state == "draft"


def test_upsert_pr_local_provider_stays_none():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        responses = [_row_for(task), _row_for(None)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        db.add = MagicMock(side_effect=_init_pr_defaults)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/pull-request",
            json={
                "branch_name": "feat/x",
                "base_branch": "main",
                "provider": "local",
            },
        )
    assert r.status_code == 200, r.text
    assert r.json()["pr_state"] == "none"
    # Local mode never changes state on upsert => no event.
    assert emit.await_count == 0


def test_upsert_pr_updates_when_exists_no_state_change_no_event():
    task = _make_task()
    pr = _make_pr(task.id)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/pull-request",
            json={
                "branch_name": "feat/test",
                "base_branch": "main",
                "provider": "github",
                "pr_number": 42,
                "commit_head_sha": "newsha1",
            },
        )
    assert r.status_code == 200, r.text
    # Already open and request defaulted to open => no state change => no event.
    assert emit.await_count == 0
    assert pr.commit_head_sha == "newsha1"


def test_upsert_pr_404_cross_org():
    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        return db

    app = _build_app(make_db)
    with _patch_bus(), TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{uuid.uuid4()}/pull-request",
            json={
                "branch_name": "feat/x",
                "base_branch": "main",
                "provider": "github",
            },
        )
    assert r.status_code == 404


# ── pull-request PATCH ───────────────────────────────────────────────


def test_patch_pr_state_change_emits_event():
    task = _make_task()
    pr = _make_pr(task.id, pr_state=LivingPrState.OPEN, merge_state_status=LivingMergeStateStatus.UNKNOWN)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.patch(
            f"/api/living/tasks/{task.id}/pull-request",
            json={"pr_state": "merged", "merge_state_status": "clean"},
        )
    assert r.status_code == 200, r.text
    assert emit.await_count == 1
    assert emit.await_args.args[0].pr_state == "merged"
    assert emit.await_args.args[0].merge_state_status == "clean"


def test_patch_pr_merge_state_only_no_event():
    task = _make_task()
    pr = _make_pr(task.id, pr_state=LivingPrState.OPEN, merge_state_status=LivingMergeStateStatus.UNKNOWN)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.patch(
            f"/api/living/tasks/{task.id}/pull-request",
            json={"merge_state_status": "clean"},
        )
    assert r.status_code == 200, r.text
    # merge_state_status changed but pr_state did not -> no event.
    assert emit.await_count == 0
    assert pr.merge_state_status == LivingMergeStateStatus.CLEAN


def test_patch_pr_404_when_no_pr_row():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(side_effect=[_row_for(task), _row_for(None)])
        return db

    app = _build_app(make_db)
    with _patch_bus(), TestClient(app) as c:
        r = c.patch(
            f"/api/living/tasks/{task.id}/pull-request",
            json={"pr_state": "merged"},
        )
    assert r.status_code == 404


# ── merge ────────────────────────────────────────────────────────────


def test_merge_transitions_task_to_done_and_emits():
    task = _make_task(status=LivingTaskStatus.RUNNING)
    pr = _make_pr(task.id, pr_state=LivingPrState.OPEN, merge_state_status=LivingMergeStateStatus.CLEAN)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/merge",
            json={"merge_strategy": "squash", "merged_commit_sha": "f00dbabe"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pr_state"] == "merged"
    assert body["merge_strategy"] == "squash"
    assert body["commit_head_sha"] == "f00dbabe"
    assert body["merged_at"] is not None
    assert task.status == LivingTaskStatus.DONE
    assert task.completed_at is not None
    assert emit.await_count == 1
    assert emit.await_args.args[0].merge_strategy == "squash"
    assert emit.await_args.args[0].provider == "github"


def test_merge_local_provider_event_carries_local():
    task = _make_task(status=LivingTaskStatus.RUNNING)
    pr = _make_pr(
        task.id,
        provider=LivingPrProvider.LOCAL,
        pr_number=None,
        pr_state=LivingPrState.NONE,
    )

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus() as emit, TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/merge",
            json={"merge_strategy": "merge", "merged_commit_sha": "abc1234"},
        )
    assert r.status_code == 200, r.text
    assert emit.await_args.args[0].provider == "local"


def test_merge_404_when_no_pr_row():
    task = _make_task()

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.execute = AsyncMock(side_effect=[_row_for(task), _row_for(None)])
        return db

    app = _build_app(make_db)
    with _patch_bus(), TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/merge",
            json={"merge_strategy": "squash", "merged_commit_sha": "abc1234"},
        )
    assert r.status_code == 404


def test_merge_does_not_overwrite_terminal_status():
    task = _make_task(status=LivingTaskStatus.CANCELLED)
    pr = _make_pr(task.id, pr_state=LivingPrState.OPEN)

    def make_db():
        db = AsyncMock()
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        responses = [_row_for(task), _row_for(pr)]

        async def _execute(stmt):
            return responses.pop(0)

        db.execute = AsyncMock(side_effect=_execute)
        return db

    app = _build_app(make_db)
    with _patch_bus(), TestClient(app) as c:
        r = c.post(
            f"/api/living/tasks/{task.id}/merge",
            json={"merge_strategy": "squash", "merged_commit_sha": "abc1234"},
        )
    assert r.status_code == 200, r.text
    # Task stays cancelled; we don't override a terminal state.
    assert task.status == LivingTaskStatus.CANCELLED


# ── auth gate ────────────────────────────────────────────────────────


def test_endpoints_require_auth():
    """Without overriding the principal, the real auth dep runs and 401s."""
    app = FastAPI()
    app.include_router(pull_requests_router)

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        yield db

    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as c:
        cases = [
            (
                f"/api/living/tasks/{uuid.uuid4()}/branch-pushed",
                "POST",
                {"branch_name": "x", "commit_sha": "abc1"},
            ),
            (
                f"/api/living/tasks/{uuid.uuid4()}/pull-request",
                "POST",
                {
                    "branch_name": "x",
                    "base_branch": "main",
                    "provider": "github",
                },
            ),
            (
                f"/api/living/tasks/{uuid.uuid4()}/pull-request",
                "PATCH",
                {"pr_state": "open"},
            ),
            (
                f"/api/living/tasks/{uuid.uuid4()}/merge",
                "POST",
                {
                    "merge_strategy": "squash",
                    "merged_commit_sha": "abc1234",
                },
            ),
        ]
        for url, method, body in cases:
            r = c.request(method, url, json=body)
            assert r.status_code == 401, f"{method} {url}: {r.status_code}"
