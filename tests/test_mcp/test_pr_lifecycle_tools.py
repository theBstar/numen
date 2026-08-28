"""Tests for the WS2 MCP tools update_pr_state + get_pr_state.

These tests target the tool functions directly (not the FastMCP wrappers)
because they share the underlying service module with the REST API tests
under tests/test_living/test_pull_requests.py - which already cover the
service end-to-end. This file focuses on the action discriminator + error
envelope translation.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.tools import get_pr_state, update_pr_state
from tests.conftest import TEST_ORG_ID

TASK_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")


def _mock_pr(**overrides):
    pr = MagicMock()
    pr.id = uuid.UUID("00000000-0000-0000-0000-000000000300")
    pr.task_id = TASK_ID
    pr.org_id = TEST_ORG_ID
    pr.branch_name = overrides.get("branch_name", "feat/x")
    pr.base_branch = overrides.get("base_branch", "develop")
    pr.commit_head_sha = overrides.get("commit_head_sha", "abcd1234")
    pr.provider = MagicMock(value=overrides.get("provider_value", "github"))
    pr.pr_number = overrides.get("pr_number", 42)
    pr.pr_url = overrides.get("pr_url", "https://github.com/o/r/pull/42")
    pr.pr_state = MagicMock(value=overrides.get("pr_state_value", "open"))
    pr.merge_state_status = MagicMock(value=overrides.get("merge_state_status_value", "clean"))
    pr.merge_strategy = (
        MagicMock(value=overrides["merge_strategy_value"])
        if "merge_strategy_value" in overrides
        else None
    )
    from datetime import datetime, timezone
    pr.created_at = datetime.now(timezone.utc)
    pr.updated_at = datetime.now(timezone.utc)
    pr.merged_at = overrides.get("merged_at")
    return pr


# ── update_pr_state ─────────────────────────────────────────────────────


async def test_invalid_action_returns_invalid_argument():
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(db, TEST_ORG_ID, str(TASK_ID), action="open_window")
    )
    assert out["error"]["code"] == "invalid_argument"
    assert "branch_pushed" in out["error"]["message"]


async def test_invalid_task_uuid_returns_invalid_uuid():
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(db, TEST_ORG_ID, "not-a-uuid", action="branch_pushed")
    )
    assert out["error"]["code"] == "invalid_uuid"


async def test_branch_pushed_missing_args_returns_invalid_argument():
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(db, TEST_ORG_ID, str(TASK_ID), action="branch_pushed")
    )
    assert out["error"]["code"] == "invalid_argument"


@patch("src.services.pr_lifecycle.record_branch_pushed")
async def test_branch_pushed_happy_path(mock_record):
    mock_record.return_value = None
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="branch_pushed", branch_name="feat/x", commit_sha="abcd1234",
        )
    )
    assert out == {"ok": True, "action": "branch_pushed"}
    mock_record.assert_awaited_once()


@patch("src.services.pr_lifecycle.upsert_pull_request")
async def test_link_action_returns_pr_dict(mock_upsert):
    mock_upsert.return_value = _mock_pr()
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="link",
            branch_name="feat/x",
            base_branch="develop",
            provider="github",
            pr_number=42,
            pr_url="https://github.com/o/r/pull/42",
        )
    )
    assert out["ok"] is True
    assert out["action"] == "link"
    assert out["pr"]["pr_number"] == 42
    assert out["pr"]["provider"] == "github"


async def test_link_invalid_provider_returns_invalid_argument():
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="link",
            branch_name="feat/x",
            base_branch="develop",
            provider="bitbucket",  # not a valid LivingPrProvider
        )
    )
    assert out["error"]["code"] == "invalid_argument"
    assert "provider" in out["error"]["message"]


@patch("src.services.pr_lifecycle.patch_pull_request")
async def test_patch_action_invalid_pr_state_returns_invalid_status(mock_patch):
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="patch",
            pr_state="explosively_open",
        )
    )
    assert out["error"]["code"] == "invalid_status"
    mock_patch.assert_not_called()


@patch("src.services.pr_lifecycle.patch_pull_request")
async def test_patch_action_happy_path(mock_patch):
    mock_patch.return_value = _mock_pr(pr_state_value="merged")
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="patch",
            pr_state="merged",
        )
    )
    assert out["ok"] is True
    assert out["action"] == "patch"
    assert out["pr"]["pr_state"] == "merged"


async def test_merge_missing_args_returns_invalid_argument():
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(db, TEST_ORG_ID, str(TASK_ID), action="merge")
    )
    assert out["error"]["code"] == "invalid_argument"


@patch("src.services.pr_lifecycle.record_merge")
async def test_merge_happy_path(mock_merge):
    mock_merge.return_value = _mock_pr(pr_state_value="merged", merge_strategy_value="squash")
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="merge",
            merge_strategy="squash",
            merged_commit_sha="deadbeef",
        )
    )
    assert out["ok"] is True
    assert out["action"] == "merge"
    assert out["pr"]["pr_state"] == "merged"
    assert out["pr"]["merge_strategy"] == "squash"


@patch("src.services.pr_lifecycle.record_merge")
async def test_merge_invalid_strategy_returns_invalid_argument(mock_merge):
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="merge",
            merge_strategy="cherry_pick_with_flair",
            merged_commit_sha="deadbeef",
        )
    )
    assert out["error"]["code"] == "invalid_argument"
    mock_merge.assert_not_called()


@patch("src.services.pr_lifecycle.upsert_pull_request")
async def test_service_task_not_found_translates_to_envelope(mock_upsert):
    from src.services.pr_lifecycle import PrServiceError, PrServiceErrorCode
    mock_upsert.side_effect = PrServiceError(
        PrServiceErrorCode.TASK_NOT_FOUND, "Task not found in this org."
    )
    db = AsyncMock()
    out = json.loads(
        await update_pr_state(
            db, TEST_ORG_ID, str(TASK_ID),
            action="link", branch_name="b", base_branch="develop", provider="github",
        )
    )
    assert out["error"]["code"] == "task_not_found"
    assert out["error"]["suggested_next_tool"] == "list_tasks"


# ── get_pr_state ────────────────────────────────────────────────────────


async def test_get_pr_state_invalid_uuid():
    db = AsyncMock()
    out = json.loads(await get_pr_state(db, TEST_ORG_ID, "not-a-uuid"))
    assert out["error"]["code"] == "invalid_uuid"


@patch("src.services.pr_lifecycle.get_pr_for_task")
async def test_get_pr_state_returns_null_when_no_pr(mock_get):
    mock_get.return_value = None
    db = AsyncMock()
    out = json.loads(await get_pr_state(db, TEST_ORG_ID, str(TASK_ID)))
    assert out == {"pr": None, "task_id": str(TASK_ID)}


@patch("src.services.pr_lifecycle.get_pr_for_task")
async def test_get_pr_state_returns_pr_dict(mock_get):
    mock_get.return_value = _mock_pr()
    db = AsyncMock()
    out = json.loads(await get_pr_state(db, TEST_ORG_ID, str(TASK_ID)))
    assert out["pr"]["pr_number"] == 42
    assert out["pr"]["task_id"] == str(TASK_ID)
