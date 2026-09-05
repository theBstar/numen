"""Enum columns hand back an enum or a plain string depending on where the row
came from, and the MCP serializers assumed only the first.

`create_task` crashed with "'str' object has no attribute 'value'" against a
live stack: the entity was written, then serializing the response raised, so the
caller saw a failure for a task that existed. Every enum field in a response has
the same exposure.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from src.mcp.serializers import edge_to_dict, entity_to_dict
from src.shared.types import EdgeType, EntityType, SourceType


def _entity(type_value, source_value):
    return SimpleNamespace(
        id=uuid4(),
        canonical_name="Ship the thing",
        type=type_value,
        source=source_value,
        properties={"status": "todo"},
        created_at=datetime(2026, 9, 5, tzinfo=timezone.utc),
        updated_at=None,
    )


@pytest.mark.parametrize(
    "type_value,source_value",
    [
        (EntityType.TASK, SourceType.MANUAL),
        ("task", "manual"),
        (EntityType.TASK, "manual"),
        ("task", SourceType.MANUAL),
    ],
    ids=["both-enum", "both-str", "mixed-a", "mixed-b"],
)
def test_entity_serializes_whether_enums_arrive_as_enums_or_strings(
    type_value, source_value
):
    out = entity_to_dict(_entity(type_value, source_value))
    assert out["type"] == "task"
    assert out["source"] == "manual"


def test_entity_tolerates_missing_enums():
    out = entity_to_dict(_entity(None, None))
    assert out["type"] is None
    assert out["source"] is None


@pytest.mark.parametrize(
    "edge_type", [EdgeType.CONTAINS, "contains"], ids=["enum", "str"]
)
def test_edge_serializes_either_form(edge_type):
    edge = SimpleNamespace(
        id=uuid4(),
        from_entity_id=uuid4(),
        to_entity_id=uuid4(),
        type=edge_type,
        weight=1.0,
        confidence=0.9,
        last_active_at=None,
    )
    assert edge_to_dict(edge)["type"] == "contains"
