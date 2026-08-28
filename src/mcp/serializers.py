"""Shared serialization helpers for MCP tools and resources."""

from __future__ import annotations

from src.shared.models import Edge, Entity


def entity_to_dict(e: Entity) -> dict:
    """Convert an Entity to a JSON-friendly dict."""
    props = e.properties or {}
    return {
        "id": str(e.id),
        "name": e.canonical_name,
        "type": e.type.value if e.type else None,
        "source": e.source.value if e.source else None,
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
        "type": e.type.value if e.type else None,
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
