"""Wiki generator must filter out PrdBlocks of archived PRDs.

Regression: deleted PRDs were leaking back into the wiki because the
generator reads PrdBlock unconditionally. We now fetch the archived
entity_id set from FalkorDB and exclude those blocks.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.prd import wiki_generator
from src.shared.types import PrdStatus

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ACTIVE_ID = uuid.UUID("00000000-0000-0000-0000-000000000090")
ARCHIVED_ID = uuid.UUID("00000000-0000-0000-0000-000000000091")


def _mk_graph_entity(eid: uuid.UUID, prd_status: str):
    ent = MagicMock()
    ent.id = eid
    ent.properties = {"prd_status": prd_status, "node_type": "document"}
    return ent


class _FakeBlock:
    def __init__(self, entity_id: uuid.UUID):
        self.entity_id = entity_id
        self.org_id = TEST_ORG_ID
        self.block_type = "heading"
        self.heading_level = 1
        self.slug = "overview"
        self.position = 1.0
        self.content = {"type": "heading", "content": [{"type": "text", "text": "T"}]}


def _mk_db_returning(blocks_for_active: list, blocks_for_archived: list):
    """Mock db.execute. Extract the NOT IN set from the compiled statement by
    reading the statement's bound parameter values, then filter in Python.
    """
    all_blocks = list(blocks_for_active) + list(blocks_for_archived)

    async def execute(stmt, *a, **kw):
        sql = str(stmt).lower()
        if "prd_blocks" not in sql:
            r = MagicMock()
            r.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=[]))
            )
            return r

        excluded: set[uuid.UUID] = set()
        try:
            compiled = stmt.compile()
            values = []
            for val in compiled.params.values():
                if isinstance(val, (list, tuple, set)):
                    values.extend(val)
                else:
                    values.append(val)
            for val in values:
                if isinstance(val, uuid.UUID):
                    excluded.add(val)
                else:
                    try:
                        excluded.add(uuid.UUID(str(val)))
                    except (ValueError, TypeError):
                        continue
        except Exception:
            pass
        excluded.discard(TEST_ORG_ID)

        if excluded:
            filtered = [b for b in all_blocks if b.entity_id not in excluded]
        else:
            filtered = all_blocks

        r = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=filtered)
        r.scalars = MagicMock(return_value=scalars)
        return r

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


@pytest.mark.asyncio
async def test_generate_skips_blocks_of_archived_prds():
    active_block = _FakeBlock(ACTIVE_ID)
    archived_block = _FakeBlock(ARCHIVED_ID)

    db = _mk_db_returning([active_block], [archived_block])

    graph_entities = [
        _mk_graph_entity(ACTIVE_ID, PrdStatus.DRAFT.value),
        _mk_graph_entity(ARCHIVED_ID, PrdStatus.ARCHIVED.value),
    ]

    with patch.object(
        wiki_generator,
        "list_entities",
        AsyncMock(return_value=graph_entities),
    ):
        structures = await wiki_generator._parse_prd_structures(db, TEST_ORG_ID)

    entity_ids_seen = {s.entity_id for s in structures}
    assert str(ACTIVE_ID) in entity_ids_seen
    assert str(ARCHIVED_ID) not in entity_ids_seen


@pytest.mark.asyncio
async def test_generate_includes_all_when_nothing_archived():
    active_block = _FakeBlock(ACTIVE_ID)
    db = _mk_db_returning([active_block], [])

    with patch.object(
        wiki_generator,
        "list_entities",
        AsyncMock(return_value=[_mk_graph_entity(ACTIVE_ID, PrdStatus.DRAFT.value)]),
    ):
        structures = await wiki_generator._parse_prd_structures(db, TEST_ORG_ID)

    entity_ids_seen = {s.entity_id for s in structures}
    assert str(ACTIVE_ID) in entity_ids_seen


@pytest.mark.asyncio
async def test_generate_handles_string_properties():
    """props can come back as a JSON-serialized string from FalkorDB."""
    ent = MagicMock()
    ent.id = ARCHIVED_ID
    ent.properties = json.dumps(
        {"prd_status": PrdStatus.ARCHIVED.value, "node_type": "document"}
    )

    db = _mk_db_returning([], [_FakeBlock(ARCHIVED_ID)])

    with patch.object(
        wiki_generator, "list_entities", AsyncMock(return_value=[ent])
    ):
        structures = await wiki_generator._parse_prd_structures(db, TEST_ORG_ID)

    assert structures == []
