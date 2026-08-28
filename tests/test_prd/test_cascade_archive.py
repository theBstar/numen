"""Unit tests for cascade_archive_prd orchestrator.

Covers: audit log, wiki ref pruning, ARCHIVED status write, edge deletion,
cache invalidation, regen scheduling, folder recursion, missing-entity 404,
and content preservation (blocks/versions are NOT deleted).
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.prd import deletion
from src.shared.types import EdgeType, PrdStatus

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
CHILD_ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000071")


def _mk_entity(
    entity_id: uuid.UUID = TEST_ENTITY_ID,
    prd_status: str = PrdStatus.DRAFT.value,
    title: str = "My PRD",
):
    entity = MagicMock()
    entity.id = entity_id
    entity.canonical_name = title
    entity.properties = {
        "prd_status": prd_status,
        "node_type": "document",
        "canonical_name": title,
    }
    return entity


def _patch_cascade_deps(
    *,
    entity=None,
    children: list[uuid.UUID] | None = None,
    block_count: int = 0,
):
    """Return a context-manager dict of patches used by every cascade test."""
    if entity is None:
        entity = _mk_entity()

    edges = []
    for child_id in children or []:
        edge = MagicMock()
        edge.to_entity_id = child_id
        edges.append(edge)

    return {
        "get_entity": patch.object(
            deletion, "get_entity", AsyncMock(return_value=entity)
        ),
        "get_edges": patch.object(
            deletion, "get_edges", AsyncMock(return_value=edges)
        ),
        "count_blocks": patch.object(
            deletion, "_count_blocks", AsyncMock(return_value=block_count)
        ),
        "prune": patch.object(deletion, "_prune_wiki_refs", AsyncMock()),
        "update_entity": patch.object(deletion, "update_entity", AsyncMock()),
        "delete_edges": patch.object(
            deletion, "delete_edges_for_entity", AsyncMock(return_value=3)
        ),
        "invalidate": patch.object(deletion, "invalidate_wiki_cache", AsyncMock()),
        "schedule": patch.object(deletion, "_schedule_wiki_regen", MagicMock()),
    }


async def _run_cascade(mock_db, patches):
    with patches["get_entity"], patches["get_edges"], patches[
        "count_blocks"
    ], patches["prune"] as prune, patches["update_entity"] as update_entity, patches[
        "delete_edges"
    ] as delete_edges, patches[
        "invalidate"
    ] as invalidate, patches[
        "schedule"
    ] as schedule:
        await deletion.cascade_archive_prd(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)
    return {
        "prune": prune,
        "update_entity": update_entity,
        "delete_edges": delete_edges,
        "invalidate": invalidate,
        "schedule": schedule,
    }


@pytest.mark.asyncio
async def test_cascade_archive_sets_prd_status_archived(mock_db):
    patches = _patch_cascade_deps()
    calls = await _run_cascade(mock_db, patches)
    props = calls["update_entity"].call_args.kwargs["properties"]
    assert props["prd_status"] == PrdStatus.ARCHIVED.value


@pytest.mark.asyncio
async def test_cascade_archive_writes_audit_log(mock_db):
    patches = _patch_cascade_deps(block_count=7)
    await _run_cascade(mock_db, patches)

    added = [c.args[0] for c in mock_db.add.call_args_list]
    audit_entries = [a for a in added if getattr(a, "action", None) == "prd.archived"]
    assert len(audit_entries) == 1
    log = audit_entries[0]
    assert log.resource_type == "prd"
    assert log.resource_id == TEST_ENTITY_ID
    assert log.org_id == TEST_ORG_ID
    assert log.details["block_count"] == 7
    assert log.details["previous_status"] == PrdStatus.DRAFT.value


@pytest.mark.asyncio
async def test_cascade_archive_prunes_wiki_refs(mock_db):
    patches = _patch_cascade_deps()
    calls = await _run_cascade(mock_db, patches)
    calls["prune"].assert_awaited_once_with(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)


@pytest.mark.asyncio
async def test_cascade_archive_deletes_graph_edges(mock_db):
    patches = _patch_cascade_deps()
    calls = await _run_cascade(mock_db, patches)
    calls["delete_edges"].assert_awaited_once_with(
        mock_db, TEST_ENTITY_ID, org_id=TEST_ORG_ID
    )


@pytest.mark.asyncio
async def test_cascade_archive_does_not_hard_delete_entity(mock_db):
    """The Entity node survives as the undo handle."""
    patches = _patch_cascade_deps()
    with patch.object(
        deletion.falkor_repository if hasattr(deletion, "falkor_repository") else deletion,
        "delete_org_entities",
        AsyncMock(),
        create=True,
    ) as would_hard_delete:
        await _run_cascade(mock_db, patches)
    would_hard_delete.assert_not_called()


@pytest.mark.asyncio
async def test_cascade_archive_invalidates_wiki_cache(mock_db):
    patches = _patch_cascade_deps()
    calls = await _run_cascade(mock_db, patches)
    calls["invalidate"].assert_awaited_once_with(TEST_ORG_ID)


@pytest.mark.asyncio
async def test_cascade_archive_schedules_regen(mock_db):
    patches = _patch_cascade_deps()
    calls = await _run_cascade(mock_db, patches)
    calls["schedule"].assert_called_once_with(TEST_ORG_ID)


@pytest.mark.asyncio
async def test_cascade_archive_preserves_prd_blocks_and_versions(mock_db):
    """Cascade must NOT issue DELETE statements against PrdBlock/PrdVersion."""
    patches = _patch_cascade_deps()
    await _run_cascade(mock_db, patches)

    executed_statements = [c.args[0] for c in mock_db.execute.call_args_list]
    for stmt in executed_statements:
        stmt_str = str(stmt).lower()
        assert "delete from prd_blocks" not in stmt_str
        assert "delete from prd_versions" not in stmt_str
        assert "delete from prd_media" not in stmt_str
        assert "delete from prd_comments" not in stmt_str
        assert "delete from prd_reactions" not in stmt_str


@pytest.mark.asyncio
async def test_cascade_archive_folder_recurses_into_children_depth_first(mock_db):
    """A folder with a child should archive the child first, then itself."""
    parent_entity = _mk_entity(entity_id=TEST_ENTITY_ID, title="Folder")
    child_entity = _mk_entity(entity_id=CHILD_ENTITY_ID, title="Child PRD")

    call_order: list[uuid.UUID] = []

    real_update_entity = AsyncMock(
        side_effect=lambda db, eid, **kw: call_order.append(eid)
    )

    def fake_get_entity(db, eid, **kw):
        if eid == TEST_ENTITY_ID:
            return parent_entity
        if eid == CHILD_ENTITY_ID:
            return child_entity
        return None

    child_edge = MagicMock()
    child_edge.to_entity_id = CHILD_ENTITY_ID

    with (
        patch.object(deletion, "get_entity", AsyncMock(side_effect=fake_get_entity)),
        patch.object(
            deletion,
            "get_edges",
            AsyncMock(
                side_effect=lambda db, eid, **kw: [child_edge]
                if eid == TEST_ENTITY_ID
                else []
            ),
        ),
        patch.object(deletion, "_count_blocks", AsyncMock(return_value=0)),
        patch.object(deletion, "_prune_wiki_refs", AsyncMock()),
        patch.object(deletion, "update_entity", real_update_entity),
        patch.object(deletion, "delete_edges_for_entity", AsyncMock(return_value=0)),
        patch.object(deletion, "invalidate_wiki_cache", AsyncMock()),
        patch.object(deletion, "_schedule_wiki_regen", MagicMock()),
    ):
        await deletion.cascade_archive_prd(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)

    assert call_order == [CHILD_ENTITY_ID, TEST_ENTITY_ID]


@pytest.mark.asyncio
async def test_cascade_archive_missing_entity_raises_404(mock_db):
    with patch.object(deletion, "get_entity", AsyncMock(return_value=None)):
        with pytest.raises(HTTPException) as exc_info:
            await deletion.cascade_archive_prd(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_cascade_archive_edge_query_scopes_to_outgoing_contains(mock_db):
    """Child discovery must look only at outgoing CONTAINS edges."""
    patches = _patch_cascade_deps()
    with patches["get_entity"], patches["get_edges"] as mock_get_edges, patches[
        "count_blocks"
    ], patches["prune"], patches["update_entity"], patches[
        "delete_edges"
    ], patches[
        "invalidate"
    ], patches[
        "schedule"
    ]:
        await deletion.cascade_archive_prd(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)

    call = mock_get_edges.await_args
    assert call.kwargs["edge_types"] == [EdgeType.CONTAINS]
    assert call.kwargs["direction"] == "outgoing"
    assert call.kwargs["org_id"] == TEST_ORG_ID
