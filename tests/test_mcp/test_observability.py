"""Tests for src/mcp/observability.py (WS5)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.mcp.observability import _classify_result, _redact_args, track


def test_redact_args_only_keeps_allowlisted_keys():
    out = _redact_args(
        "find_matching_task",
        {"description": "PII text here", "limit": 10, "recommend_threshold": 0.85},
    )
    assert out["safe"] == {"limit": 10, "recommend_threshold": 0.85}
    assert "description" not in out["safe"]
    assert out["args_size_bytes"] > 0


def test_redact_args_unknown_tool_keeps_nothing():
    out = _redact_args("totally_made_up_tool", {"x": 1, "y": 2})
    assert out["safe"] == {}


def test_redact_args_drops_none_values():
    out = _redact_args("list_tasks", {"status": None, "limit": 50})
    assert out["safe"] == {"limit": 50}


def test_classify_result_ok_for_normal_payload():
    out = _classify_result(json.dumps({"chunks": [], "total_tokens": 0}))
    assert out == ("ok", None)


def test_classify_result_error_extracts_code():
    out = _classify_result(
        json.dumps({"error": {"code": "task_not_found", "message": "x"}})
    )
    assert out == ("error", "task_not_found")


def test_classify_result_legacy_string_error_treated_as_ok():
    """Legacy {"error": "string"} format - we don't break on it."""
    out = _classify_result(json.dumps({"error": "old style"}))
    assert out == ("ok", None)


def test_classify_result_invalid_json_is_ok():
    out = _classify_result("not json at all")
    assert out == ("ok", None)


async def test_track_persists_call_log_on_success():
    org_id = uuid.uuid4()
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    class _Factory:
        def __call__(self):
            return _SF()

    class _SF:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    factory = _Factory()
    async with track(
        tool_name="find_matching_task",
        org_id=org_id,
        user_id=None,
        args={"limit": 10},
        session_factory=factory,
    ) as obs:
        obs.set_result(json.dumps({"candidates": []}))

    db.add.assert_called_once()
    persisted = db.add.call_args[0][0]
    assert persisted.tool_name == "find_matching_task"
    assert persisted.org_id == org_id
    assert persisted.status == "ok"
    db.commit.assert_awaited_once()


async def test_track_persists_error_status_with_code():
    org_id = uuid.uuid4()
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()

    class _Factory:
        def __call__(self):
            return _SF()

    class _SF:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *a):
            return False

    async with track(
        tool_name="get_context",
        org_id=org_id,
        user_id=None,
        args={"max_tokens": 4000},
        session_factory=_Factory(),
    ) as obs:
        obs.set_result(json.dumps({"error": {"code": "auth_required", "message": "x"}}))

    persisted = db.add.call_args[0][0]
    assert persisted.status == "error"
    assert persisted.error_code == "auth_required"


async def test_track_swallows_db_errors_silently():
    """If the call_log persist fails, the tool result must still flow through."""
    org_id = uuid.uuid4()

    class _Factory:
        def __call__(self):
            return _SF()

    class _SF:
        async def __aenter__(self):
            db = AsyncMock()
            db.add = MagicMock(side_effect=RuntimeError("DB exploded"))
            return db

        async def __aexit__(self, *a):
            return False

    # Must not raise even though add() raises
    async with track(
        tool_name="hello_numen",
        org_id=org_id,
        user_id=None,
        args={},
        session_factory=_Factory(),
    ) as obs:
        obs.set_result(json.dumps({"ok": True}))


async def test_track_no_session_factory_just_logs_to_stdout():
    """When session_factory is None (e.g. stdio mode without DB), just log."""
    async with track(
        tool_name="hello_numen",
        org_id=None,
        user_id=None,
        args={},
        session_factory=None,
    ) as obs:
        obs.set_result(json.dumps({"ok": True}))
    # No assertion - just that it didn't blow up
