"""Tests for scripts/restore_archived_prds.py."""

from __future__ import annotations

import importlib.util
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.shared.types import PrdNodeType, PrdStatus

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000071")


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "restore_archived_prds.py"
    spec = importlib.util.spec_from_file_location("restore_archived_prds", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["restore_archived_prds"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script():
    return _load_script()


def _mk_entity(prd_status: str, node_type: str = PrdNodeType.DOCUMENT.value):
    entity = MagicMock()
    entity.id = TEST_ENTITY_ID
    entity.properties = {
        "prd_status": prd_status,
        "node_type": node_type,
        "canonical_name": "Archived PRD",
    }
    return entity


@pytest.mark.asyncio
async def test_dry_run_reports_but_does_not_write(script):
    archived = _mk_entity(PrdStatus.ARCHIVED.value)

    with (
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "list_entities", AsyncMock(return_value=[archived])),
        patch.object(script, "update_entity", AsyncMock()) as mock_update,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        mock_session.return_value.__aenter__.return_value = AsyncMock()

        scanned, restored = await script.restore_org(TEST_ORG_ID, apply=False)

    assert scanned == 1
    assert restored == 1
    mock_update.assert_not_awaited()
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_apply_restores_to_draft_and_clears_cache(script):
    archived = _mk_entity(PrdStatus.ARCHIVED.value)
    db = AsyncMock()

    with (
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "list_entities", AsyncMock(return_value=[archived])),
        patch.object(script, "update_entity", AsyncMock()) as mock_update,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        mock_session.return_value.__aenter__.return_value = db

        scanned, restored = await script.restore_org(TEST_ORG_ID, apply=True)

    assert scanned == 1
    assert restored == 1

    new_props = mock_update.call_args.kwargs["properties"]
    assert new_props["prd_status"] == PrdStatus.DRAFT.value
    assert mock_update.call_args.kwargs["merge_properties"] is False
    mock_invalidate.assert_awaited_once_with(TEST_ORG_ID)


@pytest.mark.asyncio
async def test_skips_non_archived_and_non_prd_nodes(script):
    active = _mk_entity(PrdStatus.DRAFT.value)
    not_a_prd = MagicMock()
    not_a_prd.id = uuid.uuid4()
    not_a_prd.properties = {"prd_status": PrdStatus.ARCHIVED.value, "node_type": "other"}

    with (
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "list_entities", AsyncMock(return_value=[active, not_a_prd])),
        patch.object(script, "update_entity", AsyncMock()) as mock_update,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        mock_session.return_value.__aenter__.return_value = AsyncMock()

        scanned, restored = await script.restore_org(TEST_ORG_ID, apply=True)

    assert scanned == 2
    assert restored == 0
    mock_update.assert_not_awaited()
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_handles_string_properties_json(script):
    archived = MagicMock()
    archived.id = TEST_ENTITY_ID
    archived.properties = json.dumps(
        {
            "prd_status": PrdStatus.ARCHIVED.value,
            "node_type": PrdNodeType.DOCUMENT.value,
            "canonical_name": "Archived PRD",
        }
    )

    with (
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "list_entities", AsyncMock(return_value=[archived])),
        patch.object(script, "update_entity", AsyncMock()) as mock_update,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()),
    ):
        mock_session.return_value.__aenter__.return_value = AsyncMock()

        scanned, restored = await script.restore_org(TEST_ORG_ID, apply=True)

    assert scanned == 1
    assert restored == 1
    new_props = mock_update.call_args.kwargs["properties"]
    assert new_props["prd_status"] == PrdStatus.DRAFT.value
