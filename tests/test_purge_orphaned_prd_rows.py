"""Tests for scripts/purge_orphaned_prd_rows.py."""

from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ORPHAN_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
LIVE_ID = uuid.UUID("00000000-0000-0000-0000-000000000080")


def _load_script():
    path = Path(__file__).resolve().parent.parent / "scripts" / "purge_orphaned_prd_rows.py"
    spec = importlib.util.spec_from_file_location("purge_orphaned_prd_rows", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["purge_orphaned_prd_rows"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def script():
    return _load_script()


@pytest.mark.asyncio
async def test_dry_run_reports_without_deleting(script):
    graph_ids = {LIVE_ID}
    per_table = {
        "prd_blocks": {ORPHAN_ID},
        "prd_versions": {ORPHAN_ID},
        "prd_comments": set(),
        "prd_reviews": set(),
        "prd_media": set(),
        "prd_alignment_checks": set(),
    }

    # Mock the per-table counts query path: async_session / list_entities.
    with (
        patch.object(
            script, "_graph_entity_ids", AsyncMock(return_value=graph_ids)
        ),
        patch.object(
            script, "_orphaned_entity_ids", AsyncMock(return_value=per_table)
        ),
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "_delete_s3_blobs", AsyncMock(return_value=0)) as mock_s3,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        db = AsyncMock()
        db.execute = AsyncMock(
            side_effect=lambda stmt, *a, **kw: _count_result(0)
        )
        mock_session.return_value.__aenter__.return_value = db

        summary = await script.purge_org(TEST_ORG_ID, apply=False)

    assert summary["apply"] is False
    assert summary["orphaned_entity_ids"] == 1
    mock_s3.assert_not_called()
    mock_invalidate.assert_not_called()


@pytest.mark.asyncio
async def test_apply_deletes_in_fk_safe_order_and_prunes_wiki(script):
    graph_ids: set[uuid.UUID] = set()
    per_table = {
        "prd_blocks": {ORPHAN_ID},
        "prd_versions": {ORPHAN_ID},
        "prd_comments": {ORPHAN_ID},
        "prd_reviews": set(),
        "prd_media": {ORPHAN_ID},
        "prd_alignment_checks": set(),
    }

    executed_statements: list[str] = []
    storage_keys = ["orgs/x/prds/y/blob.png"]
    block_ids = [uuid.uuid4()]

    async def fake_execute(stmt, *a, **kw):
        s = str(stmt).lower()
        executed_statements.append(s)
        if "prd_blocks.id" in s and "select" in s:
            return _scalars_result(block_ids)
        if "prd_media.storage_key" in s:
            return _scalars_result(storage_keys)
        if "select count" in s:
            return _count_result(1)
        return _scalars_result([])

    with (
        patch.object(
            script, "_graph_entity_ids", AsyncMock(return_value=graph_ids)
        ),
        patch.object(
            script, "_orphaned_entity_ids", AsyncMock(return_value=per_table)
        ),
        patch.object(script, "async_session") as mock_session,
        patch.object(script, "_prune_wiki_refs", AsyncMock()) as mock_prune,
        patch.object(
            script, "_delete_s3_blobs", AsyncMock(return_value=len(storage_keys))
        ) as mock_s3,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=fake_execute)
        db.commit = AsyncMock()
        mock_session.return_value.__aenter__.return_value = db

        summary = await script.purge_org(TEST_ORG_ID, apply=True)

    delete_statements = [s for s in executed_statements if "delete from" in s]
    assert any("prd_reactions" in s for s in delete_statements)
    assert any("prd_comments" in s for s in delete_statements)
    assert any("prd_blocks" in s for s in delete_statements)
    assert any("prd_versions" in s for s in delete_statements)
    assert any("prd_media" in s for s in delete_statements)

    reactions_idx = next(i for i, s in enumerate(delete_statements) if "prd_reactions" in s)
    blocks_idx = next(i for i, s in enumerate(delete_statements) if "prd_blocks" in s)
    assert reactions_idx < blocks_idx

    mock_prune.assert_awaited()
    mock_s3.assert_awaited_once_with(storage_keys)
    mock_invalidate.assert_awaited_once_with(TEST_ORG_ID)
    assert summary["s3_blobs_deleted"] == 1


@pytest.mark.asyncio
async def test_no_orphans_skips_all_side_effects(script):
    with (
        patch.object(
            script, "_graph_entity_ids", AsyncMock(return_value={LIVE_ID})
        ),
        patch.object(
            script,
            "_orphaned_entity_ids",
            AsyncMock(
                return_value={
                    "prd_blocks": set(),
                    "prd_versions": set(),
                    "prd_comments": set(),
                    "prd_reviews": set(),
                    "prd_media": set(),
                    "prd_alignment_checks": set(),
                }
            ),
        ),
        patch.object(script, "_delete_s3_blobs", AsyncMock()) as mock_s3,
        patch.object(script, "invalidate_wiki_cache", AsyncMock()) as mock_invalidate,
    ):
        summary = await script.purge_org(TEST_ORG_ID, apply=True)

    assert summary["orphaned_entity_ids"] == 0
    mock_s3.assert_not_called()
    mock_invalidate.assert_not_called()


def _count_result(n: int):
    r = MagicMock()
    r.scalar_one = MagicMock(return_value=n)
    return r


def _scalars_result(items):
    r = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    r.scalars = MagicMock(return_value=scalars)
    return r
