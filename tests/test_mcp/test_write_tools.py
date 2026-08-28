"""Tests for MCP write tools and the keystone find_matching_task helper."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.tools import (
    append_wiki_note,
    create_task,
    find_matching_task,
    update_task_status,
)
from src.shared.types import EntityType, Priority, SourceType, TaskStatus
from tests.conftest import TEST_ORG_ID, TEST_TASK_ID

ACTOR_USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000aa")


# ── find_matching_task ────────────────────────────────────────────────


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.call_llm", create=True)
async def test_find_matching_task_uses_llm_rerank_when_available(
    mock_llm, mock_list, mock_db, mock_entity
):
    # call_llm is imported lazily inside the function; patch the lookup target
    from src.llm import client as llm_client_module

    mock_list.return_value = [mock_entity]

    async def fake_call(system, user, max_tokens=512):
        return json.dumps(
            {
                "matches": [
                    {
                        "task_id": str(mock_entity.id),
                        "confidence": 0.92,
                        "reason": "same wording",
                    }
                ]
            }
        )

    with patch.object(llm_client_module, "call_llm", side_effect=fake_call):
        result = json.loads(
            await find_matching_task(mock_db, TEST_ORG_ID, "fix the bug", limit=5)
        )

    assert result["method"] == "llm_rerank"
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["confidence"] == pytest.approx(0.92)


@patch("src.mcp.tools.list_entities")
async def test_find_matching_task_falls_back_to_substring_on_llm_failure(
    mock_list, mock_db, mock_entity
):
    mock_list.return_value = [mock_entity]

    from src.llm import client as llm_client_module

    async def fake_call(system, user, max_tokens=512):
        raise RuntimeError("OpenAI down")

    with patch.object(llm_client_module, "call_llm", side_effect=fake_call):
        result = json.loads(
            await find_matching_task(mock_db, TEST_ORG_ID, "fix the bug")
        )

    assert result["method"] == "substring_fallback"
    assert len(result["candidates"]) >= 1
    # Fallback returns confidence=null
    assert result["candidates"][0]["confidence"] is None


@patch("src.mcp.tools.list_entities")
async def test_find_matching_task_empty_when_no_candidates(mock_list, mock_db):
    mock_list.return_value = []
    result = json.loads(await find_matching_task(mock_db, TEST_ORG_ID, "anything"))
    assert result["candidates"] == []


# ── create_task ───────────────────────────────────────────────────────


def _new_entity_with(properties: dict | None = None, *, eid: uuid.UUID = TEST_TASK_ID):
    e = MagicMock()
    e.id = eid
    e.org_id = TEST_ORG_ID
    e.type = EntityType.TASK
    e.source = SourceType.MANUAL
    e.source_ids = {"manual": "mcp:test"}
    e.canonical_name = "Test task"
    e.properties = properties or {"status": TaskStatus.TODO.value, "priority": "medium"}
    e.updated_at = datetime.now(timezone.utc)
    e.created_at = datetime.now(timezone.utc)
    return e


@patch("src.mcp.tools.log_action_safely", new_callable=AsyncMock)
@patch("src.mcp.tools.upsert_edge", new_callable=AsyncMock)
@patch("src.mcp.tools.upsert_entity", new_callable=AsyncMock)
async def test_create_task_minimal_fields_persists_and_returns_entity(
    mock_upsert_entity, mock_upsert_edge, _mock_audit, mock_db
):
    new_entity = _new_entity_with()
    mock_upsert_entity.return_value = new_entity

    result = json.loads(
        await create_task(
            mock_db,
            TEST_ORG_ID,
            ACTOR_USER_ID,
            title="Test task",
            priority=Priority.MEDIUM.value,
        )
    )

    assert result["id"] == str(TEST_TASK_ID)
    mock_upsert_entity.assert_awaited_once()
    # No project / goals / assignee = no edges wired
    mock_upsert_edge.assert_not_awaited()
    mock_db.commit.assert_awaited()


@patch("src.mcp.tools.upsert_entity", new_callable=AsyncMock)
async def test_create_task_rejects_blank_title(mock_upsert_entity, mock_db):
    result = json.loads(
        await create_task(mock_db, TEST_ORG_ID, ACTOR_USER_ID, title="   ")
    )
    assert "error" in result
    mock_upsert_entity.assert_not_awaited()


@patch("src.mcp.tools.upsert_entity", new_callable=AsyncMock)
async def test_create_task_rejects_unknown_priority(mock_upsert_entity, mock_db):
    result = json.loads(
        await create_task(
            mock_db, TEST_ORG_ID, ACTOR_USER_ID, title="ok", priority="ultra"
        )
    )
    assert "error" in result
    mock_upsert_entity.assert_not_awaited()


# ── update_task_status (forward-only) ─────────────────────────────────


@patch("src.mcp.tools.log_action_safely", new_callable=AsyncMock)
@patch("src.mcp.tools.update_entity", new_callable=AsyncMock)
@patch("src.mcp.tools.get_entity", new_callable=AsyncMock)
async def test_update_task_status_advances_forward(
    mock_get_entity, mock_update_entity, _mock_audit, mock_db
):
    task = _new_entity_with({"status": TaskStatus.TODO.value})
    advanced = _new_entity_with({"status": TaskStatus.IN_PROGRESS.value})
    mock_get_entity.return_value = task
    mock_update_entity.return_value = advanced

    result = json.loads(
        await update_task_status(
            mock_db,
            TEST_ORG_ID,
            ACTOR_USER_ID,
            str(TEST_TASK_ID),
            TaskStatus.IN_PROGRESS.value,
        )
    )

    assert (result["properties"] or {}).get("status") == TaskStatus.IN_PROGRESS.value
    mock_update_entity.assert_awaited_once()


@patch("src.mcp.tools.update_entity", new_callable=AsyncMock)
@patch("src.mcp.tools.get_entity", new_callable=AsyncMock)
async def test_update_task_status_rejects_backward_transition(
    mock_get_entity, mock_update_entity, mock_db
):
    task = _new_entity_with({"status": TaskStatus.IN_REVIEW.value})
    mock_get_entity.return_value = task

    result = json.loads(
        await update_task_status(
            mock_db,
            TEST_ORG_ID,
            ACTOR_USER_ID,
            str(TEST_TASK_ID),
            TaskStatus.TODO.value,
        )
    )

    assert "error" in result
    assert "backward" in result["error"].lower()
    mock_update_entity.assert_not_awaited()


@patch("src.mcp.tools.update_entity", new_callable=AsyncMock)
@patch("src.mcp.tools.get_entity", new_callable=AsyncMock)
async def test_update_task_status_idempotent_on_same_status(
    mock_get_entity, mock_update_entity, mock_db
):
    task = _new_entity_with({"status": TaskStatus.IN_PROGRESS.value})
    mock_get_entity.return_value = task

    result = json.loads(
        await update_task_status(
            mock_db,
            TEST_ORG_ID,
            ACTOR_USER_ID,
            str(TEST_TASK_ID),
            TaskStatus.IN_PROGRESS.value,
        )
    )
    # Returns the entity untouched
    assert result["id"] == str(TEST_TASK_ID)
    mock_update_entity.assert_not_awaited()


@patch("src.mcp.tools.get_entity", new_callable=AsyncMock)
async def test_update_task_status_rejects_unknown_status(mock_get_entity, mock_db):
    result = json.loads(
        await update_task_status(
            mock_db, TEST_ORG_ID, ACTOR_USER_ID, str(TEST_TASK_ID), "shipping"
        )
    )
    assert "error" in result
    mock_get_entity.assert_not_called()


# ── append_wiki_note ──────────────────────────────────────────────────


def _wiki_feature_row(content: str = "", slug: str = "billing"):
    wf = MagicMock()
    wf.id = uuid.uuid4()
    wf.org_id = TEST_ORG_ID
    wf.slug = slug
    wf.title = "Billing"
    wf.status = "active"
    wf.summary = ""
    wf.content = content
    wf.is_manual = False
    return wf


def _user_row():
    u = MagicMock()
    u.id = ACTOR_USER_ID
    u.email = "actor@test.com"
    return u


@patch("src.mcp.tools.log_action_safely", new_callable=AsyncMock)
async def test_append_wiki_note_creates_section_when_absent(_mock_audit, mock_db):
    wf = _wiki_feature_row(content="# Billing\n\nExisting body.\n")
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wf
    mock_db.execute = AsyncMock(return_value=scalar_result)
    mock_db.get = AsyncMock(return_value=_user_row())

    result = json.loads(
        await append_wiki_note(
            mock_db, TEST_ORG_ID, ACTOR_USER_ID, "billing", "Slack DM verified."
        )
    )

    assert result["appended"] is True
    assert "## Notes from Numen MCP" in wf.content
    assert "Slack DM verified." in wf.content
    assert wf.is_manual is True


@patch("src.mcp.tools.log_action_safely", new_callable=AsyncMock)
async def test_append_wiki_note_idempotent_on_duplicate_consecutive(
    _mock_audit, mock_db
):
    # Pre-existing notes section with one entry
    seed = (
        "# Billing\n\n"
        "Body.\n\n"
        "## Notes from Numen MCP\n"
        "- 2026-05-01 12:00 UTC by actor@test.com: Slack DM verified.\n"
    )
    wf = _wiki_feature_row(content=seed)
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = wf
    mock_db.execute = AsyncMock(return_value=scalar_result)
    mock_db.get = AsyncMock(return_value=_user_row())

    # The note is the same string, but the timestamp will differ — so this
    # tests the "exact bullet match" idempotency. Inject a frozen timestamp by
    # crafting a fresh wf where the last bullet equals what the function
    # would emit. Easiest: monkeypatch datetime.now used in the module.
    import src.mcp.tools as tools_module

    fixed_now = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    class FixedDatetime:
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    with patch.object(tools_module, "datetime", FixedDatetime):
        result = json.loads(
            await append_wiki_note(
                mock_db,
                TEST_ORG_ID,
                ACTOR_USER_ID,
                "billing",
                "Slack DM verified.",
            )
        )

    assert result["appended"] is False
    assert result["reason"] == "duplicate"


async def test_append_wiki_note_rejects_missing_feature(mock_db):
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=scalar_result)

    result = json.loads(
        await append_wiki_note(
            mock_db, TEST_ORG_ID, ACTOR_USER_ID, "missing", "note"
        )
    )
    assert "error" in result


async def test_append_wiki_note_rejects_empty_note(mock_db):
    result = json.loads(
        await append_wiki_note(mock_db, TEST_ORG_ID, ACTOR_USER_ID, "billing", "   ")
    )
    assert "error" in result
