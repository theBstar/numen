"""Tests for MCP serialization helpers."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.mcp.serializers import edge_to_dict, entity_to_dict, urgency_score_to_dict
from src.shared.types import EdgeType, EntityType, SourceType


def test_entity_to_dict_full():
    entity = MagicMock()
    entity.id = "abc-123"
    entity.canonical_name = "Test Entity"
    entity.type = EntityType.TASK
    entity.source = SourceType.LINEAR
    entity.properties = {"status": "in_progress"}
    entity.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    result = entity_to_dict(entity)
    assert result["id"] == "abc-123"
    assert result["name"] == "Test Entity"
    assert result["type"] == "task"
    assert result["source"] == "linear"
    assert result["properties"]["status"] == "in_progress"
    assert "2026-01-01" in result["created_at"]


def test_entity_to_dict_none_fields():
    entity = MagicMock()
    entity.id = "abc-123"
    entity.canonical_name = "Minimal"
    entity.type = None
    entity.source = None
    entity.properties = None
    entity.created_at = None
    entity.updated_at = None

    result = entity_to_dict(entity)
    assert result["type"] is None
    assert result["source"] is None
    assert result["properties"] == {}
    assert result["created_at"] is None


def test_edge_to_dict():
    edge = MagicMock()
    edge.id = "edge-1"
    edge.from_entity_id = "from-1"
    edge.to_entity_id = "to-1"
    edge.type = EdgeType.BLOCKS
    edge.weight = 1.0
    edge.confidence = 0.9
    edge.last_active_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = edge_to_dict(edge)
    assert result["type"] == "blocks"
    assert result["weight"] == 1.0
    assert result["confidence"] == 0.9


def test_urgency_score_to_dict_without_entity():
    score = MagicMock()
    score.entity_id = "entity-1"
    score.score = 85.0
    score.score_components = {"staleness_days": 0.5}
    score.provenance = [{"factor": "blocking"}]
    score.computed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = urgency_score_to_dict(score)
    assert result["score"] == 85.0
    assert "entity" not in result


def test_urgency_score_to_dict_with_entity():
    score = MagicMock()
    score.entity_id = "entity-1"
    score.score = 85.0
    score.score_components = {}
    score.provenance = []
    score.computed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    entity = MagicMock()
    entity.id = "entity-1"
    entity.canonical_name = "My Task"
    entity.type = EntityType.TASK
    entity.source = SourceType.LINEAR
    entity.properties = {}
    entity.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    entity.updated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    result = urgency_score_to_dict(score, entity)
    assert result["entity"]["name"] == "My Task"
