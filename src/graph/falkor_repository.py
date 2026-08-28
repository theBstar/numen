"""FalkorDB entity and edge CRUD operations.

Drop-in replacement for ``repository.py`` - identical function signatures
and return types. All callers pass ``db: AsyncSession`` as first arg;
we accept it for API compatibility but don't use it (FalkorDB has its
own connection via ``falkor_client``).

Returned objects support attribute access (``.id``, ``.type``, etc.)
via ``GraphNode`` / ``GraphEdge`` wrappers so connectors, event handlers,
and API routes work unchanged.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from src.graph.falkor_client import get_org_graph
from src.graph.schema import entity_label
from src.shared.types import (
    ConnectorSyncResult,
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    SourceType,
)

logger = logging.getLogger(__name__)


# ── Wrapper classes for attribute access ─────────────────────────────


class GraphNode:
    """Thin wrapper over a dict that supports attribute access.

    Mimics SQLAlchemy Entity model so callers like connectors and
    event handlers can access ``.id``, ``.type``, ``.properties`` etc.
    """

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"GraphNode has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __repr__(self):
        return f"GraphNode({self._data.get('type', '?')}:{self._data.get('id', '?')[:8]})"

    def get(self, key, default=None):
        return self._data.get(key, default)


class GraphEdge:
    """Thin wrapper over a dict for edge attribute access."""

    def __init__(self, data: dict):
        self._data = data

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(f"GraphEdge has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            self._data[name] = value

    def __repr__(self):
        return f"GraphEdge({self._data.get('type', '?')})"

    def get(self, key, default=None):
        return self._data.get(key, default)


# ── Helpers ──────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    """UTC datetime for timestamps."""
    return datetime.now(timezone.utc)


def _utcnow_iso() -> str:
    """ISO timestamp string for FalkorDB properties."""
    return _utcnow().isoformat()


def _build_source_key(source: SourceType, source_ids: dict[str, str]) -> str:
    """Build a deterministic key for entity matching."""
    sorted_ids = sorted(source_ids.items())
    return f"{source.value}:{json.dumps(dict(sorted_ids), sort_keys=True)}"


def _node_to_dict(node) -> dict:
    """Convert a FalkorDB node result to a plain dict."""
    props = dict(node.properties) if hasattr(node, "properties") else dict(node)
    for key in ("source_ids", "properties"):
        val = props.get(key)
        if isinstance(val, str):
            try:
                props[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return props


def _node_to_entity(node) -> GraphNode:
    """Convert a FalkorDB node result to a GraphNode."""
    d = _node_to_dict(node)
    # Ensure datetime fields are actual datetime objects
    for ts_field in ("created_at", "updated_at"):
        val = d.get(ts_field)
        if isinstance(val, str) and val:
            try:
                d[ts_field] = datetime.fromisoformat(val)
            except ValueError:
                pass
    # Ensure UUID fields are actual UUID objects so comparisons with
    # FastAPI path parameters (which are UUID) work correctly.
    for uid_field in ("id", "org_id"):
        val = d.get(uid_field)
        if isinstance(val, str) and val:
            try:
                d[uid_field] = UUID(val)
            except ValueError:
                pass
    return GraphNode(d)


def _edge_to_dict(rel) -> dict:
    """Convert a FalkorDB relationship result to a plain dict."""
    props = dict(rel.properties) if hasattr(rel, "properties") else dict(rel)
    for key in ("evidence",):
        val = props.get(key)
        if isinstance(val, str):
            try:
                props[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                pass
    return props


def _edge_to_obj(rel) -> GraphEdge:
    """Convert a FalkorDB relationship result to a GraphEdge."""
    d = _edge_to_dict(rel)
    for ts_field in ("first_seen_at", "last_active_at"):
        val = d.get(ts_field)
        if isinstance(val, str) and val:
            try:
                d[ts_field] = datetime.fromisoformat(val)
            except ValueError:
                pass
    return GraphEdge(d)


def _extract_org_id(entity_or_edge) -> UUID:
    """Extract org_id from an EntityCreate or EdgeCreate."""
    return entity_or_edge.org_id


# ── Entity CRUD ──────────────────────────────────────────────────────


async def upsert_entity(db, entity: EntityCreate) -> GraphNode:
    """Insert or update an entity in FalkorDB.

    Uses Cypher MERGE on ``source_key`` so concurrent syncs can't create duplicates
    (the read-then-create pattern had a race window that produced duplicate PRs).

    ``db`` is accepted for API compatibility but not used.
    """
    org_id = _extract_org_id(entity)
    graph = await get_org_graph(org_id)
    label = entity_label(entity.type)
    source_key = _build_source_key(entity.source, entity.source_ids)
    now = _utcnow()
    now_iso = now.isoformat()
    new_id = str(uuid.uuid4())

    # MERGE locks on source_key; ON CREATE initializes, ON MATCH updates.
    # Label is interpolated because MERGE patterns don't accept parameterized labels.
    result = await graph.query(
        f"MERGE (n:Entity:{label} {{source_key: $sk}}) "
        "ON CREATE SET "
        "  n.id = $new_id, n.org_id = $org_id, n.type = $type, n.source = $source, "
        "  n.source_ids = $sids, n.canonical_name = $name, n.properties = $props, "
        "  n.created_at = $now, n.updated_at = $now "
        "ON MATCH SET "
        "  n.canonical_name = $name, n.properties = $props, n.updated_at = $now "
        "RETURN n",
        {
            "sk": source_key,
            "new_id": new_id,
            "org_id": str(org_id),
            "type": entity.type.value,
            "source": entity.source.value,
            "sids": json.dumps(entity.source_ids),
            "name": entity.canonical_name,
            "props": json.dumps(entity.properties),
            "now": now_iso,
        },
    )

    # On MATCH we still need to additively merge source_ids (don't clobber).
    node = _node_to_dict(result.result_set[0][0])
    existing_sids = node.get("source_ids", {})
    if isinstance(existing_sids, str):
        existing_sids = json.loads(existing_sids)

    # If we matched an existing node, its source_ids came from the DB and may
    # contain keys the caller didn't pass (e.g. cross-source enrichment).
    was_created = node.get("id") == new_id
    if not was_created:
        merged_sids = {**existing_sids, **entity.source_ids}
        if merged_sids != existing_sids:
            await graph.query(
                "MATCH (n:Entity) WHERE n.source_key = $sk SET n.source_ids = $sids",
                {"sk": source_key, "sids": json.dumps(merged_sids)},
            )
            node["source_ids"] = merged_sids
        else:
            node["source_ids"] = existing_sids
    else:
        node["source_ids"] = entity.source_ids

    node["canonical_name"] = entity.canonical_name
    node["properties"] = entity.properties
    node["updated_at"] = now
    if "created_at" in node and isinstance(node["created_at"], str):
        try:
            node["created_at"] = datetime.fromisoformat(node["created_at"])
        except ValueError:
            pass
    return GraphNode(node)


async def upsert_edge(db, edge: EdgeCreate) -> GraphEdge:
    """Insert or update an edge in FalkorDB."""
    org_id = _extract_org_id(edge)
    graph = await get_org_graph(org_id)
    now = _utcnow()
    now_iso = now.isoformat()
    edge_type_upper = edge.type.value.upper()

    # Check if edge exists
    result = await graph.query(
        "MATCH (a:Entity {id: $from_id})-[r]->(b:Entity {id: $to_id}) WHERE type(r) = $rtype RETURN r",
        {
            "from_id": str(edge.from_entity_id),
            "to_id": str(edge.to_entity_id),
            "rtype": edge_type_upper,
        },
    )

    if result.result_set:
        existing = _edge_to_dict(result.result_set[0][0])
        existing_evidence = existing.get("evidence", [])
        if isinstance(existing_evidence, str):
            existing_evidence = json.loads(existing_evidence)
        for item in edge.evidence:
            if item not in existing_evidence:
                existing_evidence.append(item)

        await graph.query(
            "MATCH (a:Entity {id: $from_id})-[r]->(b:Entity {id: $to_id}) "
            "WHERE type(r) = $rtype "
            "SET r.weight = $w, r.confidence = $c, "
            "r.evidence = $ev, r.last_active_at = $now "
            "RETURN r",
            {
                "from_id": str(edge.from_entity_id),
                "to_id": str(edge.to_entity_id),
                "rtype": edge_type_upper,
                "w": edge.weight,
                "c": edge.confidence,
                "ev": json.dumps(existing_evidence),
                "now": now_iso,
            },
        )

        first_seen = existing.get("first_seen_at", now_iso)
        if isinstance(first_seen, str):
            try:
                first_seen = datetime.fromisoformat(first_seen)
            except ValueError:
                first_seen = now

        return GraphEdge(
            {
                "id": existing.get("id", str(uuid.uuid4())),
                "from_entity_id": edge.from_entity_id,
                "to_entity_id": edge.to_entity_id,
                "type": edge.type,
                "weight": edge.weight,
                "confidence": edge.confidence,
                "evidence": existing_evidence,
                "first_seen_at": first_seen,
                "last_active_at": now,
            }
        )

    # Create new edge
    edge_id = str(uuid.uuid4())
    await graph.query(
        f"MATCH (a:Entity {{id: $from_id}}), (b:Entity {{id: $to_id}}) "
        f"CREATE (a)-[r:{edge_type_upper} {{"
        "id: $eid, type: $etype, weight: $w, confidence: $c, "
        "evidence: $ev, first_seen_at: $now, last_active_at: $now"
        "}]->(b) RETURN r",
        {
            "from_id": str(edge.from_entity_id),
            "to_id": str(edge.to_entity_id),
            "eid": edge_id,
            "etype": edge.type.value,
            "w": edge.weight,
            "c": edge.confidence,
            "ev": json.dumps(edge.evidence),
            "now": now_iso,
        },
    )

    return GraphEdge(
        {
            "id": edge_id,
            "from_entity_id": edge.from_entity_id,
            "to_entity_id": edge.to_entity_id,
            "type": edge.type,
            "weight": edge.weight,
            "confidence": edge.confidence,
            "evidence": edge.evidence,
            "first_seen_at": now,
            "last_active_at": now,
        }
    )


def track_edge_result(edge, result: ConnectorSyncResult) -> None:
    """Update sync result counts."""
    first = edge.first_seen_at if hasattr(edge, "first_seen_at") else edge.get("first_seen_at")
    last = edge.last_active_at if hasattr(edge, "last_active_at") else edge.get("last_active_at")
    if first == last:
        result.edges_created += 1
    else:
        result.edges_updated += 1


# ── Entity reads ──────────────────────────────────────────────────────


async def get_entity(db, entity_id: UUID, *, org_id: UUID | None = None) -> GraphNode | None:
    """Fetch a single entity by ID."""
    if org_id is None:
        return None  # FalkorDB requires org_id for graph selection
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (n:Entity {id: $id}) RETURN n LIMIT 1",
        {"id": str(entity_id)},
    )
    if not result.result_set:
        return None
    return _node_to_entity(result.result_set[0][0])


async def get_entity_or_404(
    db,
    entity_id: UUID,
    org_id: UUID | None = None,
    expected_type: EntityType | None = None,
) -> GraphNode:
    """Fetch entity or raise 404."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    if expected_type is not None and entity.type != expected_type.value:
        raise HTTPException(status_code=404, detail="Entity not found")
    return entity


async def get_entity_by_source(
    db,
    org_id: UUID,
    source: SourceType,
    source_id: str,
) -> GraphNode | None:
    """Look up an entity by source_id value. Excludes merged entities."""
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (n:Entity) WHERE n.source = $src AND n.merged_into IS NULL RETURN n",
        {"src": source.value},
    )
    for row in result.result_set:
        node = _node_to_dict(row[0])
        sids = node.get("source_ids", {})
        if isinstance(sids, str):
            sids = json.loads(sids)
        if source_id in sids.values():
            return GraphNode(node)
    return None


async def list_entities(
    db,
    org_id: UUID,
    *,
    entity_type: EntityType | None = None,
    source: SourceType | None = None,
    search: str | None = None,
    status: str | None = None,
    include_merged: bool = False,
    limit: int = 200,
    offset: int = 0,
    order_by_updated: bool = True,
) -> list[GraphNode]:
    """List entities with optional filters."""
    graph = await get_org_graph(org_id)

    wheres = []
    params: dict[str, Any] = {"lim": limit, "off": offset}

    if entity_type is not None:
        wheres.append("n.type = $etype")
        params["etype"] = entity_type.value
    if source is not None:
        wheres.append("n.source = $src")
        params["src"] = source.value
    if search:
        wheres.append("toLower(n.canonical_name) CONTAINS toLower($search)")
        params["search"] = search
    if not include_merged:
        wheres.append("n.merged_into IS NULL")

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""
    order = "ORDER BY n.updated_at DESC" if order_by_updated else ""

    result = await graph.query(
        f"MATCH (n:Entity) {where_clause} RETURN n {order} SKIP $off LIMIT $lim",
        params,
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


async def count_entities(
    db,
    org_id: UUID,
    *,
    entity_type: EntityType | None = None,
    source: SourceType | None = None,
    search: str | None = None,
    status: str | None = None,
    include_merged: bool = False,
) -> int:
    """Count entities matching filters."""
    graph = await get_org_graph(org_id)

    wheres = []
    params: dict[str, Any] = {}

    if entity_type is not None:
        wheres.append("n.type = $etype")
        params["etype"] = entity_type.value
    if source is not None:
        wheres.append("n.source = $src")
        params["src"] = source.value
    if search:
        wheres.append("toLower(n.canonical_name) CONTAINS toLower($search)")
        params["search"] = search
    if not include_merged:
        wheres.append("n.merged_into IS NULL")

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""

    result = await graph.query(
        f"MATCH (n:Entity) {where_clause} RETURN count(n) AS cnt",
        params,
    )
    return result.result_set[0][0] if result.result_set else 0


async def get_entities_by_ids(
    db,
    entity_ids: list[UUID],
    *,
    org_id: UUID | None = None,
) -> list[GraphNode]:
    """Fetch multiple entities by IDs."""
    if not entity_ids or org_id is None:
        return []
    graph = await get_org_graph(org_id)
    str_ids = [str(eid) for eid in entity_ids]
    result = await graph.query(
        "MATCH (n:Entity) WHERE n.id IN $ids RETURN n",
        {"ids": str_ids},
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


async def find_person_by_email(db, org_id: UUID, email: str) -> GraphNode | None:
    """Find a non-merged Person entity by email."""
    graph = await get_org_graph(org_id)
    email_lower = email.lower()

    result = await graph.query(
        "MATCH (n:Person) WHERE toLower(n.email) = $email AND n.merged_into IS NULL RETURN n LIMIT 1",
        {"email": email_lower},
    )
    if result.result_set:
        return _node_to_entity(result.result_set[0][0])

    # Fallback: scan source_ids
    result = await graph.query("MATCH (n:Person) WHERE n.merged_into IS NULL RETURN n")
    for row in result.result_set:
        node = _node_to_dict(row[0])
        sids = node.get("source_ids", {})
        if isinstance(sids, str):
            sids = json.loads(sids)
        if sids.get("email", "").lower() == email_lower:
            return GraphNode(node)
    return None


async def bulk_upsert_entities(db, entities: list[EntityCreate]) -> list[GraphNode]:
    """Batch upsert entities."""
    return [await upsert_entity(db, e) for e in entities]


async def bulk_upsert_edges(db, edges: list[EdgeCreate]) -> list[GraphEdge]:
    """Batch upsert edges."""
    return [await upsert_edge(db, e) for e in edges]


# ── Entity writes ─────────────────────────────────────────────────────


async def update_entity(
    db,
    entity_id: UUID,
    *,
    org_id: UUID | None = None,
    canonical_name: str | None = None,
    properties: dict[str, Any] | None = None,
    merge_properties: bool = False,
) -> GraphNode:
    """Update an entity's mutable fields."""
    if org_id is None:
        raise HTTPException(status_code=400, detail="org_id required")

    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    graph = await get_org_graph(org_id)
    sets = ["n.updated_at = $now"]
    params: dict[str, Any] = {"id": str(entity_id), "now": _utcnow_iso()}

    if canonical_name is not None:
        sets.append("n.canonical_name = $name")
        params["name"] = canonical_name

    if properties is not None:
        if merge_properties:
            existing_props = entity.properties
            if isinstance(existing_props, str):
                existing_props = json.loads(existing_props)
            merged = {**existing_props, **properties}
            sets.append("n.properties = $props")
            params["props"] = json.dumps(merged)
        else:
            sets.append("n.properties = $props")
            params["props"] = json.dumps(properties)

    result = await graph.query(
        f"MATCH (n:Entity {{id: $id}}) SET {', '.join(sets)} RETURN n",
        params,
    )
    if result.result_set:
        return _node_to_entity(result.result_set[0][0])
    return entity


async def delete_entity(db, entity_id: UUID, *, org_id: UUID | None = None) -> None:
    """Delete an entity and all its edges. Requires org_id for graph selection."""
    if org_id is None:
        return
    graph = await get_org_graph(org_id)
    await graph.query(
        "MATCH (n:Entity {id: $id}) DETACH DELETE n",
        {"id": str(entity_id)},
    )


async def delete_org_entities(db, org_id: UUID) -> int:
    """Bulk-delete all entities for an org."""
    graph = await get_org_graph(org_id)
    result = await graph.query("MATCH (n) DETACH DELETE n RETURN count(n) AS cnt")
    return result.result_set[0][0] if result.result_set else 0


# ── Edge reads ────────────────────────────────────────────────────────


async def get_edges(
    db,
    entity_id: UUID,
    edge_types: list[EdgeType] | None = None,
    direction: str = "both",
    *,
    org_id: UUID | None = None,
) -> list[GraphEdge]:
    """Get edges for an entity."""
    if org_id is None:
        return []
    graph = await get_org_graph(org_id)
    eid = str(entity_id)

    if direction == "outgoing":
        pattern = "(a:Entity {id: $eid})-[r]->(b:Entity)"
    elif direction == "incoming":
        pattern = "(b:Entity)-[r]->(a:Entity {id: $eid})"
    else:
        pattern = "(a:Entity {id: $eid})-[r]-(b:Entity)"

    result = await graph.query(
        f"MATCH {pattern} RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rtype",
        {"eid": eid},
    )

    edges = []
    for row in result.result_set:
        e = _edge_to_dict(row[0])
        e["from_entity_id"] = row[1]
        e["to_entity_id"] = row[2]
        e["type"] = EdgeType(row[3].lower()) if row[3] else e.get("type")
        if edge_types and e.get("type") not in edge_types:
            continue
        edges.append(GraphEdge(e))
    return edges


async def get_edge_by_id(db, edge_id: UUID, *, org_id: UUID | None = None) -> GraphEdge | None:
    """Fetch a single edge by its ID."""
    if org_id is None:
        return None
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) WHERE r.id = $eid RETURN r, a.id, b.id, type(r) LIMIT 1",
        {"eid": str(edge_id)},
    )
    if not result.result_set:
        return None
    e = _edge_to_dict(result.result_set[0][0])
    e["from_entity_id"] = result.result_set[0][1]
    e["to_entity_id"] = result.result_set[0][2]
    e["type"] = (
        EdgeType(result.result_set[0][3].lower()) if result.result_set[0][3] else e.get("type")
    )
    return GraphEdge(e)


async def get_edge_by_triple(
    db,
    from_entity_id: UUID,
    to_entity_id: UUID,
    edge_type: EdgeType,
    *,
    org_id: UUID | None = None,
) -> GraphEdge | None:
    """Find edge by unique (from, to, type) triple."""
    if org_id is None:
        return None
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (a:Entity {id: $fid})-[r]->(b:Entity {id: $tid}) WHERE type(r) = $rtype RETURN r LIMIT 1",
        {
            "fid": str(from_entity_id),
            "tid": str(to_entity_id),
            "rtype": edge_type.value.upper(),
        },
    )
    if not result.result_set:
        return None
    e = _edge_to_dict(result.result_set[0][0])
    e["from_entity_id"] = from_entity_id
    e["to_entity_id"] = to_entity_id
    e["type"] = edge_type
    return GraphEdge(e)


async def list_edges(
    db,
    *,
    org_id: UUID | None = None,
    entity_id: UUID | None = None,
    edge_type: EdgeType | None = None,
    direction: str = "both",
    from_entity_id: UUID | None = None,
    to_entity_id: UUID | None = None,
) -> list[GraphEdge]:
    """Flexible edge listing."""
    if org_id is None:
        return []
    graph = await get_org_graph(org_id)

    if from_entity_id and to_entity_id:
        pattern = "(a:Entity {id: $fid})-[r]->(b:Entity {id: $tid})"
        params: dict[str, Any] = {"fid": str(from_entity_id), "tid": str(to_entity_id)}
    elif entity_id:
        eid = str(entity_id)
        if direction == "outgoing":
            pattern = "(a:Entity {id: $eid})-[r]->(b:Entity)"
        elif direction == "incoming":
            pattern = "(b:Entity)-[r]->(a:Entity {id: $eid})"
        else:
            pattern = "(a:Entity {id: $eid})-[r]-(b:Entity)"
        params = {"eid": eid}
    else:
        pattern = "(a:Entity)-[r]->(b:Entity)"
        params = {}

    type_filter = ""
    if edge_type is not None:
        type_filter = f"WHERE type(r) = '{edge_type.value.upper()}'"

    result = await graph.query(
        f"MATCH {pattern} {type_filter} RETURN r, a.id, b.id, type(r)",
        params,
    )

    edges = []
    for row in result.result_set:
        e = _edge_to_dict(row[0])
        e["from_entity_id"] = UUID(row[1]) if isinstance(row[1], str) else row[1]
        e["to_entity_id"] = UUID(row[2]) if isinstance(row[2], str) else row[2]
        e["type"] = EdgeType(row[3].lower()) if row[3] else e.get("type")
        edges.append(GraphEdge(e))
    return edges


async def get_connected_entity_ids(
    db,
    entity_id: UUID,
    edge_type: EdgeType,
    direction: str = "outgoing",
    *,
    org_id: UUID | None = None,
) -> list[UUID]:
    """Get IDs of entities connected via a specific edge type."""
    if org_id is None:
        return []
    graph = await get_org_graph(org_id)
    eid = str(entity_id)
    rtype = edge_type.value.upper()

    if direction == "outgoing":
        cypher = "MATCH (a:Entity {id: $eid})-[r]->(b:Entity) WHERE type(r) = $rtype RETURN b.id"
    elif direction == "incoming":
        cypher = "MATCH (b:Entity)-[r]->(a:Entity {id: $eid}) WHERE type(r) = $rtype RETURN b.id"
    else:
        cypher = "MATCH (a:Entity {id: $eid})-[r]-(b:Entity) WHERE type(r) = $rtype RETURN b.id"

    result = await graph.query(cypher, {"eid": eid, "rtype": rtype})
    return [UUID(row[0]) for row in result.result_set]


async def get_entities_via_edge(
    db,
    entity_id: UUID,
    edge_type: EdgeType,
    direction: str = "outgoing",
    target_type: EntityType | None = None,
    *,
    org_id: UUID | None = None,
) -> list[GraphNode]:
    """Get entities connected via a specific edge type."""
    if org_id is None:
        return []
    graph = await get_org_graph(org_id)
    eid = str(entity_id)
    rtype = edge_type.value.upper()
    params: dict[str, Any] = {"eid": eid, "rtype": rtype}

    if direction == "outgoing":
        pattern = "(a:Entity {id: $eid})-[r]->(b:Entity)"
    elif direction == "incoming":
        pattern = "(b:Entity)-[r]->(a:Entity {id: $eid})"
    else:
        pattern = "(a:Entity {id: $eid})-[r]-(b:Entity)"

    where = "WHERE type(r) = $rtype"
    if target_type is not None:
        where += " AND b.type = $ttype"
        params["ttype"] = target_type.value

    cypher = f"MATCH {pattern} {where} RETURN b"
    result = await graph.query(cypher, params)
    return [_node_to_entity(row[0]) for row in result.result_set]


async def count_edges(
    db,
    entity_id: UUID,
    edge_type: EdgeType,
    direction: str = "outgoing",
    *,
    org_id: UUID | None = None,
) -> int:
    """Count edges of a specific type for an entity."""
    if org_id is None:
        return 0
    graph = await get_org_graph(org_id)
    eid = str(entity_id)
    rtype = edge_type.value.upper()

    if direction == "outgoing":
        cypher = "MATCH (a:Entity {id: $eid})-[r]->(b:Entity) WHERE type(r) = $rtype RETURN count(r) AS cnt"
    elif direction == "incoming":
        cypher = "MATCH (b:Entity)-[r]->(a:Entity {id: $eid}) WHERE type(r) = $rtype RETURN count(r) AS cnt"
    else:
        cypher = "MATCH (a:Entity {id: $eid})-[r]-(b:Entity) WHERE type(r) = $rtype RETURN count(r) AS cnt"

    result = await graph.query(cypher, {"eid": eid, "rtype": rtype})
    return result.result_set[0][0] if result.result_set else 0


# ── Edge writes ───────────────────────────────────────────────────────


async def delete_edge_by_id(db, edge_id: UUID, *, org_id: UUID | None = None) -> bool:
    """Delete edge by ID."""
    if org_id is None:
        return False
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH ()-[r]->() WHERE r.id = $eid DELETE r RETURN count(r) AS cnt",
        {"eid": str(edge_id)},
    )
    return (result.result_set[0][0] if result.result_set else 0) > 0


async def delete_edges(
    db,
    entity_id: UUID,
    edge_type: EdgeType | None = None,
    direction: str = "both",
) -> int:
    """Delete edges for an entity."""
    return 0


async def delete_edges_for_entity(
    db,
    entity_id: UUID,
    *,
    org_id: UUID,
) -> int:
    """Delete every edge in both directions touching an Entity node. Returns count."""
    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (a:Entity)-[r]-(b:Entity) "
        "WHERE a.id = $eid OR b.id = $eid "
        "DELETE r RETURN count(r) AS cnt",
        {"eid": str(entity_id)},
    )
    return result.result_set[0][0] if result.result_set else 0


async def replace_edges(
    db,
    entity_id: UUID,
    edge_type: EdgeType,
    direction: str,
    new_target_ids: list[UUID],
    org_id: UUID,
    *,
    weight: float = 1.0,
    confidence: float = 1.0,
    evidence: list[dict] | None = None,
) -> list[GraphEdge]:
    """Replace all edges of a type/direction with new targets."""
    # Delete existing
    graph = await get_org_graph(org_id)
    eid = str(entity_id)
    rtype = edge_type.value.upper()

    if direction == "outgoing":
        pattern = f"(a:Entity {{id: $eid}})-[r:{rtype}]->(b:Entity)"
    else:
        pattern = f"(b:Entity)-[r:{rtype}]->(a:Entity {{id: $eid}})"

    await graph.query(f"MATCH {pattern} DELETE r", {"eid": eid})

    # Create new edges
    new_edges = []
    for target_id in new_target_ids:
        from_id = entity_id if direction == "outgoing" else target_id
        to_id = target_id if direction == "outgoing" else entity_id
        edge = await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=from_id,
                to_entity_id=to_id,
                type=edge_type,
                weight=weight,
                confidence=confidence,
                evidence=evidence or [],
            ),
        )
        new_edges.append(edge)
    return new_edges


async def delete_org_edges(db, org_id: UUID) -> int:
    """Bulk-delete all edges for an org."""
    graph = await get_org_graph(org_id)
    result = await graph.query("MATCH ()-[r]->() DELETE r RETURN count(r) AS cnt")
    return result.result_set[0][0] if result.result_set else 0
