"""Tests for FalkorDB repository functions:
get_entities_via_edge, count_edges, get_connected_entity_ids."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.falkor_repository import (
    count_edges,
    count_entities,
    find_person_by_email,
    get_connected_entity_ids,
    get_entities_via_edge,
    get_entity_by_source,
    list_entities,
)
from src.shared.types import EdgeType, EntityType, SourceType


@pytest.fixture
def org_id():
    return uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


@pytest.fixture
def entity_id():
    return uuid.uuid4()


def _make_falkor_node(entity_id: uuid.UUID, entity_type: str = "task") -> MagicMock:
    """Create a mock FalkorDB node with properties dict."""
    node = MagicMock()
    node.properties = {
        "id": str(entity_id),
        "type": entity_type,
        "canonical_name": f"Test {entity_type}",
        "org_id": str(uuid.uuid4()),
        "source": "linear",
        "source_ids": "{}",
        "properties": "{}",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    return node


# ── get_entities_via_edge ────────────────────────────────────────────


class TestGetEntitiesViaEdge:
    @pytest.mark.asyncio
    async def test_returns_empty_when_org_id_none(self, entity_id):
        db = AsyncMock()
        result = await get_entities_via_edge(db, entity_id, EdgeType.OWNS, direction="outgoing", org_id=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_entities_outgoing(self, org_id, entity_id):
        target_id = uuid.uuid4()
        mock_node = _make_falkor_node(target_id, "task")
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[mock_node]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_entities_via_edge(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.OWNS,
                direction="outgoing",
                org_id=org_id,
            )

        assert len(result) == 1
        assert result[0].id == target_id
        # Verify outgoing Cypher pattern was used
        call_args = mock_graph.query.call_args
        cypher = call_args[0][0]
        assert "(a:Entity" in cypher
        assert ")-[r]->(b:Entity)" in cypher or "-[r]->" in cypher

    @pytest.mark.asyncio
    async def test_returns_entities_incoming(self, org_id, entity_id):
        target_id = uuid.uuid4()
        mock_node = _make_falkor_node(target_id, "person")
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[mock_node]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_entities_via_edge(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.OWNS,
                direction="incoming",
                org_id=org_id,
            )

        assert len(result) == 1
        cypher = mock_graph.query.call_args[0][0]
        # Incoming means: (b:Entity)-[r]->(a:Entity {id: ...})
        assert "-[r]->(a:Entity" in cypher

    @pytest.mark.asyncio
    async def test_filters_by_target_type(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await get_entities_via_edge(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.TAGGED_TO,
                direction="outgoing",
                target_type=EntityType.GOAL,
                org_id=org_id,
            )

        cypher = mock_graph.query.call_args[0][0]
        params = mock_graph.query.call_args[0][1]
        assert "b.type" in cypher
        assert params.get("ttype") == "goal"

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_results(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_entities_via_edge(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.OWNS,
                direction="outgoing",
                org_id=org_id,
            )

        assert result == []


# ── count_edges ──────────────────────────────────────────────────────


class TestCountEdges:
    @pytest.mark.asyncio
    async def test_returns_zero_when_org_id_none(self, entity_id):
        db = AsyncMock()
        result = await count_edges(db, entity_id, EdgeType.BLOCKS, direction="outgoing", org_id=None)
        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_count_outgoing(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[3]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await count_edges(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="outgoing",
                org_id=org_id,
            )

        assert result == 3
        cypher = mock_graph.query.call_args[0][0]
        assert "count(r)" in cypher.lower() or "count" in cypher.lower()

    @pytest.mark.asyncio
    async def test_returns_count_incoming(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[5]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await count_edges(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="incoming",
                org_id=org_id,
            )

        assert result == 5
        cypher = mock_graph.query.call_args[0][0]
        assert "-[r]->(a:Entity" in cypher

    @pytest.mark.asyncio
    async def test_returns_zero_when_no_edges(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[0]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await count_edges(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="outgoing",
                org_id=org_id,
            )

        assert result == 0

    @pytest.mark.asyncio
    async def test_returns_zero_when_empty_result_set(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await count_edges(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="outgoing",
                org_id=org_id,
            )

        assert result == 0


# ── get_connected_entity_ids ─────────────────────────────────────────


class TestGetConnectedEntityIds:
    @pytest.mark.asyncio
    async def test_returns_empty_when_org_id_none(self, entity_id):
        db = AsyncMock()
        result = await get_connected_entity_ids(db, entity_id, EdgeType.BLOCKS, direction="outgoing", org_id=None)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_ids_outgoing(self, org_id, entity_id):
        target_id1 = uuid.uuid4()
        target_id2 = uuid.uuid4()
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[str(target_id1)], [str(target_id2)]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_connected_entity_ids(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="outgoing",
                org_id=org_id,
            )

        assert len(result) == 2
        assert target_id1 in result
        assert target_id2 in result
        # All returned items should be UUID objects
        for item in result:
            assert isinstance(item, uuid.UUID)

    @pytest.mark.asyncio
    async def test_returns_ids_incoming(self, org_id, entity_id):
        target_id = uuid.uuid4()
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = [[str(target_id)]]
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_connected_entity_ids(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.OWNS,
                direction="incoming",
                org_id=org_id,
            )

        assert len(result) == 1
        cypher = mock_graph.query.call_args[0][0]
        assert "-[r]->(a:Entity" in cypher

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_results(self, org_id, entity_id):
        mock_graph = AsyncMock()
        mock_result = MagicMock()
        mock_result.result_set = []
        mock_graph.query = AsyncMock(return_value=mock_result)

        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            result = await get_connected_entity_ids(
                db=AsyncMock(),
                entity_id=entity_id,
                edge_type=EdgeType.BLOCKS,
                direction="outgoing",
                org_id=org_id,
            )

        assert result == []


# ── merged_into filtering in read paths ──────────────────────────────


class TestMergedIntoFiltering:
    """Merged entities must be excluded from listings and cross-source lookups."""

    @pytest.mark.asyncio
    async def test_list_entities_default_excludes_merged(self, org_id):
        mock_graph = AsyncMock()
        mock_graph.query.return_value = MagicMock(result_set=[])
        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await list_entities(db=AsyncMock(), org_id=org_id, entity_type=EntityType.PERSON)
        cypher = mock_graph.query.call_args[0][0]
        assert "n.merged_into IS NULL" in cypher

    @pytest.mark.asyncio
    async def test_list_entities_include_merged_true_omits_filter(self, org_id):
        mock_graph = AsyncMock()
        mock_graph.query.return_value = MagicMock(result_set=[])
        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await list_entities(
                db=AsyncMock(),
                org_id=org_id,
                entity_type=EntityType.PERSON,
                include_merged=True,
            )
        cypher = mock_graph.query.call_args[0][0]
        assert "merged_into" not in cypher

    @pytest.mark.asyncio
    async def test_count_entities_default_excludes_merged(self, org_id):
        mock_graph = AsyncMock()
        mock_graph.query.return_value = MagicMock(result_set=[[0]])
        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await count_entities(db=AsyncMock(), org_id=org_id)
        cypher = mock_graph.query.call_args[0][0]
        assert "n.merged_into IS NULL" in cypher

    @pytest.mark.asyncio
    async def test_get_entity_by_source_excludes_merged(self, org_id):
        mock_graph = AsyncMock()
        mock_graph.query.return_value = MagicMock(result_set=[])
        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await get_entity_by_source(
                db=AsyncMock(),
                org_id=org_id,
                source=SourceType.SLACK,
                source_id="U123",
            )
        cypher = mock_graph.query.call_args[0][0]
        assert "n.merged_into IS NULL" in cypher

    @pytest.mark.asyncio
    async def test_find_person_by_email_excludes_merged(self, org_id):
        mock_graph = AsyncMock()
        # Both the indexed and fallback scans return nothing; we only check the Cypher.
        mock_graph.query.return_value = MagicMock(result_set=[])
        with patch("src.graph.falkor_repository.get_org_graph", return_value=mock_graph):
            await find_person_by_email(db=AsyncMock(), org_id=org_id, email="alice@test.com")
        # Both queries should filter merged
        for call in mock_graph.query.call_args_list:
            cypher = call[0][0]
            assert "merged_into IS NULL" in cypher
