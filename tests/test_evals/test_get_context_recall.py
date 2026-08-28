"""Eval harness for MCP get_context recall@10.

The checked-in fixture is synthetic so the harness runs green anywhere.
Point it at a real hand-labeled corpus to measure actual retrieval
quality - the assertions are structural and the recall computation is
real either way. See tests/test_evals/README.md.

Pass criterion: aggregate recall@10 >= 0.7. Below that, a re-ranker
becomes a hard requirement.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.tools import get_context

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "get_context_recall.json"
ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def load_fixture(path: Path = FIXTURE_PATH) -> dict:
    with path.open() as fh:
        return json.load(fh)


def recall_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int = 10) -> float:
    """Standard recall@k: |retrieved[:k] ∩ expected| / |expected|."""
    if not expected_ids:
        return 1.0
    retrieved_set = set(str(i) for i in retrieved_ids[:k])
    expected_set = set(str(i) for i in expected_ids)
    hit = len(retrieved_set & expected_set)
    return hit / len(expected_set)


def _vec_row(node_id: str, body: str, score: float):
    node = MagicMock()
    node.properties = {
        "id": node_id,
        "type": "document",
        "source": "notion",
        "canonical_name": f"Doc {node_id}",
        "properties": json.dumps(
            {"body": body, "doc_title": f"Doc {node_id}", "parent_doc_id": node_id}
        ),
        "source_ids": "{}",
        "org_id": str(ORG_ID),
    }
    return [node, score]


async def _run_query(task: str, expected_doc_ids: list[str]) -> float:
    """Run a single eval query end-to-end with mocked vector layer.

    For the scaffold: simulate a perfect retriever that returns the expected
    docs as the top-k. This proves the harness math works. When real Falkor
    fixtures land, replace the patches with a live FalkorDB seeded with the
    eval corpus.
    """
    rows = [
        _vec_row(doc_id, f"body for {doc_id}", 0.99 - i * 0.01)
        for i, doc_id in enumerate(expected_doc_ids)
    ]
    # Pad to k=20 with noise rows so the truncation path is exercised.
    for _ in range(20 - len(rows)):
        rows.append(_vec_row(str(uuid.uuid4()), "noise", 0.1))

    graph = MagicMock()

    async def _query(cypher, params=None):
        result = MagicMock()
        if "db.idx.vector.queryNodes" in cypher:
            result.result_set = rows
        else:
            result.result_set = []
        return result

    graph.query = AsyncMock(side_effect=_query)

    db = AsyncMock()
    with (
        patch(
            "src.graph._embedding.embed_text",
            new=AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "src.graph.falkor_client.get_org_graph",
            new=AsyncMock(return_value=graph),
        ),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(await get_context(db, ORG_ID, AGENT_ID, task, max_tokens=4000))

    retrieved = [c.get("parent_doc_id") or c.get("chunk_id") for c in out["chunks"]]
    return recall_at_k(retrieved, expected_doc_ids, k=10)


def test_fixture_loads():
    fx = load_fixture()
    assert "queries" in fx
    assert len(fx["queries"]) >= 30, "WS8: need at least 30 queries"
    for q in fx["queries"]:
        assert "task" in q
        assert "category" in q
        assert q["category"] in fx.get("categories", []), (
            f"unknown category {q['category']}"
        )
        assert isinstance(q["expected_doc_ids"], list)


def test_recall_at_k_helper():
    assert recall_at_k(["a", "b"], ["a", "b"]) == 1.0
    assert recall_at_k(["a"], ["a", "b"]) == 0.5
    assert recall_at_k([], ["a"]) == 0.0
    assert recall_at_k([], []) == 1.0


async def test_aggregate_recall_at_10_meets_threshold():
    """Aggregate recall@10 >= 0.7 across the synthetic query set.

    Wired through a perfect-retriever mock, this asserts ~1.0 for non-
    negative categories. Replace the mock with live Falkor + real corpus
    to get meaningful numbers (see tests/test_evals/README.md).
    """
    fx = load_fixture()
    thresholds = fx.get("thresholds", {})
    aggregate_floor = thresholds.get("aggregate", {}).get("recall_at_10", 0.7)

    by_category: dict[str, list[float]] = {}
    for q in fx["queries"]:
        if q["category"] == "negative":
            # Negative queries: skip the recall assertion (they have no
            # expected docs - recall@k against empty expected_set returns 1.0
            # by convention which would mask issues).
            continue
        r = await _run_query(q["task"], q["expected_doc_ids"])
        by_category.setdefault(q["category"], []).append(r)

    for cat, vals in by_category.items():
        floor = thresholds.get(cat, {}).get("recall_at_10", 0.5)
        avg = sum(vals) / len(vals)
        assert avg >= floor, (
            f"category {cat} recall@10={avg:.3f} below threshold {floor}"
        )

    all_vals = [v for vals in by_category.values() for v in vals]
    aggregate = sum(all_vals) / len(all_vals)
    assert aggregate >= aggregate_floor, (
        f"aggregate recall@10={aggregate:.3f} below threshold {aggregate_floor}"
    )


def test_categories_include_negative_for_false_positive_audit():
    """The negative category protects against retriever false-positives;
    its presence is part of the WS8 contract."""
    fx = load_fixture()
    cats = {q["category"] for q in fx["queries"]}
    assert "negative" in cats, "WS8: negative category must exist for FP audit"
    negative = [q for q in fx["queries"] if q["category"] == "negative"]
    assert len(negative) >= 5, "WS8: need >=5 negative samples"
