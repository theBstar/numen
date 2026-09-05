"""Shared serialization helpers for MCP tools and resources."""

from __future__ import annotations

from enum import Enum

from src.shared.models import Edge, Entity


def _enum_value(value) -> str | None:
    """Return the wire form of an enum column, whichever form it arrives in.

    SQLAlchemy hands back an Enum member for a loaded row but the raw string
    for one that was just constructed and flushed. Assuming the member crashed
    create_task after it had already written the entity, so the caller saw a
    failure for a task that existed.
    """
    if value is None:
        return None
    return value.value if isinstance(value, Enum) else str(value)


def entity_to_dict(e: Entity) -> dict:
    """Convert an Entity to a JSON-friendly dict."""
    props = e.properties or {}
    return {
        "id": str(e.id),
        "name": e.canonical_name,
        "type": _enum_value(e.type),
        "source": _enum_value(e.source),
        "properties": props,
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "updated_at": e.updated_at.isoformat() if e.updated_at else None,
    }


def edge_to_dict(e: Edge) -> dict:
    """Convert an Edge to a JSON-friendly dict."""
    return {
        "id": str(e.id),
        "from_entity_id": str(e.from_entity_id),
        "to_entity_id": str(e.to_entity_id),
        "type": _enum_value(e.type),
        "weight": e.weight,
        "confidence": e.confidence,
        "last_active_at": e.last_active_at.isoformat() if e.last_active_at else None,
    }


def urgency_score_to_dict(score, entity: Entity | None = None) -> dict:
    """Convert an UrgencyScoreCache row to a JSON-friendly dict."""
    result = {
        "entity_id": str(score.entity_id),
        "score": score.score,
        "components": score.score_components,
        "provenance": score.provenance,
        "computed_at": score.computed_at.isoformat() if score.computed_at else None,
    }
    if entity:
        result["entity"] = entity_to_dict(entity)
    return result
