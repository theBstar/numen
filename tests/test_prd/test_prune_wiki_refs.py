"""Unit tests for _prune_wiki_refs JSONB surgery.

- Multi-source features keep the row with the archived entity_id filtered out.
- Sole-source features delete the row.
- WikiConcept follows the same pattern on prd_references.
- WikiProductSummary.prd_hashes drops the key; row deleted only if dict empty.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.prd import deletion

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ARCHIVED_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
OTHER_ID = uuid.UUID("00000000-0000-0000-0000-000000000080")


def _result(items):
    """Mimic SQLAlchemy result.scalars().all() / scalar_one_or_none()."""
    r = MagicMock()
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=items)
    r.scalars = MagicMock(return_value=scalars)
    r.scalar_one_or_none = MagicMock(
        return_value=items[0] if items else None
    )
    return r


def _mk_db(features=None, concepts=None, summary=None):
    """Build an AsyncMock db whose execute() returns the right result per model.

    Detection is by string match against the statement - good enough for this unit test.
    """
    features = features or []
    concepts = concepts or []

    async def execute(stmt, *a, **kw):
        s = str(stmt).lower()
        if "wiki_features" in s and "select" in s:
            return _result(features)
        if "wiki_concepts" in s and "select" in s:
            return _result(concepts)
        if "wiki_product_summary" in s and "select" in s:
            return _result([summary] if summary else [])
        return _result([])

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=execute)
    return db


def _feature(source_ids, refs=None):
    f = MagicMock()
    f.id = uuid.uuid4()
    f.source_entity_ids = list(source_ids)
    f.prd_references = refs if refs is not None else [{"entity_id": str(s)} for s in source_ids]
    return f


def _concept(source_ids):
    c = MagicMock()
    c.id = uuid.uuid4()
    c.prd_references = [{"entity_id": str(s)} for s in source_ids]
    return c


def _summary(hashes: dict):
    s = MagicMock()
    s.id = uuid.uuid4()
    s.prd_hashes = dict(hashes)
    return s


def _delete_statements(db):
    return [
        str(c.args[0]).lower()
        for c in db.execute.call_args_list
        if "delete from" in str(c.args[0]).lower()
    ]


def _update_statements(db):
    return [
        c for c in db.execute.call_args_list if "update" in str(c.args[0]).lower()
    ]


@pytest.mark.asyncio
async def test_prune_keeps_feature_when_other_sources_remain():
    feat = _feature([ARCHIVED_ID, OTHER_ID])
    db = _mk_db(features=[feat])

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert not any("wiki_features" in s for s in deletes)
    updates = _update_statements(db)
    feature_updates = [u for u in updates if "wiki_features" in str(u.args[0]).lower()]
    assert feature_updates, "expected an UPDATE to patch source_entity_ids"


@pytest.mark.asyncio
async def test_prune_deletes_feature_when_last_source_removed():
    feat = _feature([ARCHIVED_ID])
    db = _mk_db(features=[feat])

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert any("wiki_features" in s for s in deletes)


@pytest.mark.asyncio
async def test_prune_deletes_concept_when_last_ref_removed():
    con = _concept([ARCHIVED_ID])
    db = _mk_db(concepts=[con])

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert any("wiki_concepts" in s for s in deletes)


@pytest.mark.asyncio
async def test_prune_keeps_concept_when_other_refs_remain():
    con = _concept([ARCHIVED_ID, OTHER_ID])
    db = _mk_db(concepts=[con])

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert not any("wiki_concepts" in s for s in deletes)


@pytest.mark.asyncio
async def test_prune_removes_product_summary_hash_for_archived():
    summary = _summary({str(ARCHIVED_ID): "abc", str(OTHER_ID): "def"})
    db = _mk_db(summary=summary)

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert not any("wiki_product_summary" in s for s in deletes)
    updates = _update_statements(db)
    assert any("wiki_product_summary" in str(u.args[0]).lower() for u in updates)


@pytest.mark.asyncio
async def test_prune_deletes_product_summary_when_empty():
    summary = _summary({str(ARCHIVED_ID): "abc"})
    db = _mk_db(summary=summary)

    await deletion._prune_wiki_refs(db, TEST_ORG_ID, ARCHIVED_ID)

    deletes = _delete_statements(db)
    assert any("wiki_product_summary" in s for s in deletes)
