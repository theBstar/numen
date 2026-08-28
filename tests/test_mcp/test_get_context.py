"""Tests for the MCP get_context tool (Lane B / Living)."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.tools import get_context
from tests.conftest import TEST_ORG_ID

OTHER_ORG_ID = uuid.UUID("99999999-9999-9999-9999-999999999999")
AGENT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TASK_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _vector_row(node_id: str, body: str, score: float, *, org_id=None, parent=None):
    """Build a Falkor-style (node, score) row mock."""
    node = MagicMock()
    node.properties = {
        "id": node_id,
        "type": "document",
        "source": "notion",
        "canonical_name": f"Doc {node_id}",
        "properties": json.dumps(
            {
                "body": body,
                "doc_title": f"Doc {node_id}",
                "doc_url": f"https://notion/{node_id}",
                "parent_doc_id": parent or node_id,
            }
        ),
        "source_ids": "{}",
        "org_id": str(org_id or TEST_ORG_ID),
    }
    return [node, score]


def _make_graph(vector_rows, hop_rows=None):
    graph = MagicMock()

    async def _query(cypher, params=None):
        result = MagicMock()
        if "db.idx.vector.queryNodes" in cypher:
            result.result_set = vector_rows
        else:
            result.result_set = hop_rows or []
        return result

    graph.query = AsyncMock(side_effect=_query)
    return graph


@pytest.fixture
def patched_embed():
    with patch("src.graph._embedding.embed_text", new=AsyncMock(return_value=[0.1] * 1536)):
        yield


async def test_get_context_happy_path(patched_embed, mock_db):
    rows = [
        _vector_row("aaaaaaaa-1111-1111-1111-111111111111", "Passkey body one.", 0.91),
        _vector_row("bbbbbbbb-2222-2222-2222-222222222222", "iOS 16 fallback body.", 0.85),
    ]
    graph = _make_graph(rows)

    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(
            await get_context(
                mock_db,
                TEST_ORG_ID,
                AGENT_ID,
                "implement passkey fallback for iOS 16",
                task_id=TASK_ID,
                max_tokens=4000,
            )
        )

    assert "chunks" in out
    assert len(out["chunks"]) == 2
    assert out["chunks"][0]["doc_title"].startswith("Doc")
    assert out["chunks"][0]["score"] == pytest.approx(0.91)
    assert out["total_tokens"] > 0
    assert "fetched_at" in out


async def test_get_context_empty_graph(patched_embed, mock_db):
    graph = _make_graph([])
    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])) as emit,
    ):
        out = json.loads(
            await get_context(
                mock_db, TEST_ORG_ID, AGENT_ID, "anything", max_tokens=500
            )
        )
    assert out["chunks"] == []
    assert out["total_tokens"] == 0
    assert emit.await_count == 1
    event = emit.await_args.args[0]
    assert event.result_count == 0


async def test_get_context_max_tokens_zero(patched_embed, mock_db):
    """max_tokens=0 returns empty immediately and emits a zero-result event."""
    with patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])) as emit:
        out = json.loads(
            await get_context(
                mock_db, TEST_ORG_ID, AGENT_ID, "anything", max_tokens=0
            )
        )
    assert out["chunks"] == []
    assert out["total_tokens"] == 0
    assert emit.await_count == 1


async def test_get_context_truncates_oversized_chunk(patched_embed, mock_db):
    """If a single top chunk's body > max_tokens, it is truncated, not dropped."""
    body = (
        "Sentence one is here. Sentence two follows. " * 200
    )  # ~9000 chars / ~2250 tokens
    rows = [_vector_row("11111111-1111-1111-1111-111111111111", body, 0.9)]
    graph = _make_graph(rows)
    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(
            await get_context(
                mock_db, TEST_ORG_ID, AGENT_ID, "task", max_tokens=100
            )
        )
    assert len(out["chunks"]) == 1
    assert out["chunks"][0].get("truncated") is True
    assert out["total_tokens"] <= 100
    # Sentence-boundary preserved: the truncated body should end with "." or
    # whitespace, not mid-word.
    assert out["chunks"][0]["body"].rstrip().endswith(".")


async def test_get_context_embedding_unavailable_503(mock_db):
    with patch(
        "src.graph._embedding.embed_text",
        new=AsyncMock(side_effect=RuntimeError("openai down")),
    ):
        out = json.loads(
            await get_context(mock_db, TEST_ORG_ID, AGENT_ID, "task")
        )
    assert out.get("status") == 503
    assert "Embedding" in out["error"]


async def test_get_context_falkor_unavailable_503(patched_embed, mock_db):
    with patch(
        "src.graph.falkor_client.get_org_graph",
        new=AsyncMock(side_effect=RuntimeError("falkor down")),
    ):
        out = json.loads(
            await get_context(mock_db, TEST_ORG_ID, AGENT_ID, "task")
        )
    assert out.get("status") == 503
    assert "Graph" in out["error"]


async def test_get_context_drops_cross_org_chunks(patched_embed, mock_db):
    """Defense-in-depth: if a vector hit somehow includes a foreign org_id,
    it must not appear in the response."""
    rows = [
        _vector_row(
            "cccccccc-3333-3333-3333-333333333333",
            "From other org - leak!",
            0.99,
            org_id=OTHER_ORG_ID,
        ),
        _vector_row(
            "dddddddd-4444-4444-4444-444444444444",
            "Legit chunk.",
            0.5,
        ),
    ]
    graph = _make_graph(rows)
    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(
            await get_context(mock_db, TEST_ORG_ID, AGENT_ID, "task")
        )
    bodies = [c["body"] for c in out["chunks"]]
    assert all("leak" not in b for b in bodies)
    assert any("Legit" in b for b in bodies)


async def test_get_context_emits_event_with_payload(patched_embed, mock_db):
    rows = [_vector_row("eeeeeeee-5555-5555-5555-555555555555", "body", 0.7)]
    graph = _make_graph(rows)
    captured = []

    async def _capture(event):
        captured.append(event)
        return []

    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(side_effect=_capture)),
    ):
        await get_context(
            mock_db,
            TEST_ORG_ID,
            AGENT_ID,
            "task one",
            task_id=TASK_ID,
            max_tokens=4000,
        )
    assert len(captured) == 1
    ev = captured[0]
    assert ev.org_id == TEST_ORG_ID
    assert ev.task_query == "task one"
    assert ev.agent_id == AGENT_ID
    assert ev.task_id == TASK_ID
    assert ev.result_count == 1
    assert ev.total_tokens > 0


async def test_get_context_long_task_string(patched_embed, mock_db):
    """10k-char task strings must embed and return without error."""
    rows = [_vector_row("aaaaaaaa-6666-6666-6666-666666666666", "body", 0.5)]
    graph = _make_graph(rows)
    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(
            await get_context(
                mock_db, TEST_ORG_ID, AGENT_ID, "x" * 10_000, max_tokens=4000
            )
        )
    assert "chunks" in out


async def test_get_context_neighborhood_batched_not_n_plus_one(patched_embed, mock_db):
    """Sanity: parent neighborhood expansion should be a single batch query
    over all parent ids, NOT a per-chunk loop."""
    rows = [
        _vector_row(f"aaaaaaaa-7777-7777-7777-{i:012d}", f"body {i}", 0.9 - i * 0.05)
        for i in range(5)
    ]
    graph = _make_graph(rows, hop_rows=[])
    with (
        patch("src.graph.falkor_client.get_org_graph", new=AsyncMock(return_value=graph)),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])) as batched,
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        await get_context(mock_db, TEST_ORG_ID, AGENT_ID, "task", max_tokens=4000)
    # The batched API should be called exactly once, regardless of chunk count.
    assert batched.await_count == 1
    # And graph.query should have been called twice: once for vector search,
    # once for the batched 1-hop expansion. NOT once per parent id.
    assert graph.query.await_count == 2
