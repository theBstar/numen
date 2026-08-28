"""Graph ontology - entity and edge type schemas with validation.

Inspired by TrustGraph's OWL ontology pattern: defines valid entity types,
their property schemas, and edge constraints (which entity types can connect
via which edge types). This provides schema-level validation before writes.
"""

from __future__ import annotations

from src.shared.types import EdgeType, EntityType

# ── Entity schemas ────────────────────────────────────────────────────
# Maps EntityType -> FalkorDB node label and required properties.

ENTITY_SCHEMA: dict[EntityType, dict] = {
    EntityType.PERSON: {
        "label": "Person",
        "required": ["canonical_name"],
    },
    EntityType.TASK: {
        "label": "Task",
        "required": ["canonical_name"],
    },
    EntityType.COMMIT_PR: {
        "label": "CommitPR",
        "required": ["canonical_name"],
    },
    EntityType.DEPLOY: {
        "label": "Deploy",
        "required": ["canonical_name"],
    },
    EntityType.INCIDENT: {
        "label": "Incident",
        "required": ["canonical_name"],
    },
    EntityType.ERROR_EVENT: {
        "label": "ErrorEvent",
        "required": ["canonical_name"],
    },
    EntityType.METRIC_SNAPSHOT: {
        "label": "MetricSnapshot",
        "required": ["canonical_name"],
    },
    EntityType.FEATURE: {
        "label": "Feature",
        "required": ["canonical_name"],
    },
    EntityType.GOAL: {
        "label": "Goal",
        "required": ["canonical_name"],
    },
    EntityType.DOCUMENT: {
        "label": "Document",
        "required": ["canonical_name"],
    },
    EntityType.DECISION: {
        "label": "Decision",
        "required": ["canonical_name"],
    },
    EntityType.PROJECT: {
        "label": "Project",
        "required": ["canonical_name"],
    },
}


def entity_label(entity_type: EntityType) -> str:
    """Return the FalkorDB node label for an entity type."""
    schema = ENTITY_SCHEMA.get(entity_type)
    if schema:
        return schema["label"]
    # Fallback: capitalize the type value
    return entity_type.value.replace("_", "").title()


# ── Edge constraints ──────────────────────────────────────────────────
# Maps EdgeType -> valid (from_labels, to_labels).
# Edges not listed here are unconstrained (pass validation).

EDGE_CONSTRAINTS: dict[EdgeType, dict[str, set[str]]] = {
    EdgeType.OWNS: {"from": {"Person"}, "to": {"Task", "Feature", "Document"}},
    EdgeType.BLOCKS: {"from": {"Task"}, "to": {"Task"}},
    EdgeType.DEPENDS_ON: {"from": {"Task", "Feature"}, "to": {"Task", "Feature"}},
    EdgeType.AUTHORED: {"from": {"Person"}, "to": {"CommitPR"}},
    EdgeType.MENTIONED_IN: {"from": {"Entity"}, "to": {"Entity"}},  # any-to-any
    EdgeType.SHIPS_TO: {"from": {"CommitPR"}, "to": {"Task"}},
    EdgeType.MEASURES: {"from": {"MetricSnapshot"}, "to": {"Goal"}},
    EdgeType.CAUSED_BY: {"from": {"Incident", "ErrorEvent"}, "to": {"Entity"}},
    EdgeType.TAGGED_TO: {"from": {"Task", "Feature", "Document"}, "to": {"Goal"}},
    EdgeType.CONFLICTS_WITH: {"from": {"Task"}, "to": {"Task"}},
    EdgeType.CONTAINS: {"from": {"Project", "Document"}, "to": {"Task", "Feature", "Document"}},
    EdgeType.PARENT_OF: {"from": {"Goal", "Document"}, "to": {"Goal", "Document"}},
    EdgeType.ASSIGNED_TO: {"from": {"Task"}, "to": {"Person"}},
    EdgeType.REPORTS_TO: {"from": {"Person"}, "to": {"Person"}},
    EdgeType.MEMBER_OF: {"from": {"Person"}, "to": {"Project"}},
    EdgeType.REVIEWS: {"from": {"Person"}, "to": {"CommitPR"}},
    EdgeType.DEPLOYED_BY: {"from": {"Deploy"}, "to": {"Person"}},
    EdgeType.APPROVED_BY: {"from": {"Entity"}, "to": {"Person"}},
    # Briefing-related edges (unconstrained for flexibility)
    EdgeType.SURFACED_TO: {"from": {"Entity"}, "to": {"Person"}},
    EdgeType.ACTED_ON: {"from": {"Person"}, "to": {"Entity"}},
    EdgeType.DISMISSED: {"from": {"Person"}, "to": {"Entity"}},
    EdgeType.ESCALATED_TO: {"from": {"Entity"}, "to": {"Person"}},
    EdgeType.PRECEDED_BY: {"from": {"Entity"}, "to": {"Entity"}},
    # PRD-specific edges
    EdgeType.REFERENCES: {"from": {"Document"}, "to": {"Document"}},
    EdgeType.STAKEHOLDER_OF: {"from": {"Person"}, "to": {"Document"}},
    EdgeType.REVIEWER_OF: {"from": {"Person"}, "to": {"Document"}},
    EdgeType.IMPLEMENTS: {"from": {"Task", "CommitPR"}, "to": {"Document", "Feature"}},
    EdgeType.DESIGNS_FOR: {"from": {"Entity"}, "to": {"Document"}},
    EdgeType.SECTION_LINKS_TO: {"from": {"Document"}, "to": {"Document"}},
}


def validate_edge(edge_type: EdgeType, from_label: str, to_label: str) -> None:
    """Validate an edge against ontology constraints.

    Raises ``ValueError`` if the edge type is not valid between the given
    entity labels. Edges with ``Entity`` in their constraint set accept
    any label (wildcard).
    """
    constraint = EDGE_CONSTRAINTS.get(edge_type)
    if constraint is None:
        return  # Unconstrained edge type

    from_ok = "Entity" in constraint["from"] or from_label in constraint["from"]
    to_ok = "Entity" in constraint["to"] or to_label in constraint["to"]

    if not from_ok or not to_ok:
        raise ValueError(
            f"Invalid edge: {from_label} -[{edge_type.value}]-> {to_label}. "
            f"Expected from={constraint['from']}, to={constraint['to']}"
        )
