"""Cross-source entity resolution for merging identities across connectors.

Entity data lives in FalkorDB. PostgreSQL is used only for relational data
(OrgMember, PersonResolution, LinkSuggestion).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, or_, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_client import get_org_graph
from src.graph.falkor_repository import (
    GraphNode,
    delete_edge_by_id,
    get_edge_by_triple,
    get_edges,
    get_entity,
    upsert_entity,
)
from src.shared.models import LinkSuggestion, OrgMember, PersonResolution
from src.shared.types import EntityCreate, EntityType, PersonResolutionStatus, SourceType

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def find_person(db, org_id: UUID, identifiers: dict) -> GraphNode | None:
    """Cross-source person lookup in FalkorDB. Returns None if no match found.

    Match priority:
    1. Exact email in source_ids
    2. github_id in source_ids (immutable numeric ID)
    3. github_username / github in source_ids
    4. slack_id in source_ids
    5. Exact name match (case-insensitive)

    This is the single source of truth for person matching logic.
    Both resolve_person() and resolve_or_create_person() delegate here.
    """
    email = identifiers.get("email")
    github_username = identifiers.get("github_username")
    github_id = identifiers.get("github_id")
    slack_id = identifiers.get("slack_id")
    name = identifiers.get("name", "")

    graph = await get_org_graph(org_id)
    result = await graph.query("MATCH (n:Entity) WHERE n.type = 'person' RETURN n")

    if not result.result_set:
        return None

    # Parse all person nodes once
    persons: list[tuple[dict, dict]] = []  # (node_dict, parsed_source_ids)
    for row in result.result_set:
        props = dict(row[0].properties) if hasattr(row[0], "properties") else dict(row[0])
        sids = props.get("source_ids", {})
        if isinstance(sids, str):
            try:
                sids = json.loads(sids)
            except (json.JSONDecodeError, TypeError):
                sids = {}
        persons.append((props, sids))

    # Priority 1: exact email match in source_ids
    if email:
        email_lower = email.lower()
        for props, sids in persons:
            if sids.get("email", "").lower() == email_lower:
                return _props_to_graphnode(props, sids)

    # Priority 1.5: github_id match
    if github_id:
        for props, sids in persons:
            if sids.get("github_id") == github_id:
                return _props_to_graphnode(props, sids)

    # Priority 2: github_username match (check both keys)
    if github_username:
        gh_lower = github_username.lower()
        for props, sids in persons:
            if sids.get("github_username", "").lower() == gh_lower or sids.get("github", "").lower() == gh_lower:
                return _props_to_graphnode(props, sids)

    # Priority 3: slack_id match
    if slack_id:
        for props, sids in persons:
            if sids.get("slack_id") == slack_id or sids.get("slack") == slack_id:
                return _props_to_graphnode(props, sids)

    # Priority 4: exact name match (case-insensitive), skip merged entities
    if name:
        name_lower = name.strip().lower()
        for props, sids in persons:
            if props.get("merged_into") is not None:
                continue
            cname = (props.get("canonical_name") or "").strip().lower()
            if cname == name_lower:
                return _props_to_graphnode(props, sids)

    return None


def _props_to_graphnode(props: dict, parsed_sids: dict) -> GraphNode:
    """Build a GraphNode from raw FalkorDB properties with pre-parsed source_ids."""
    d = dict(props)
    d["source_ids"] = parsed_sids
    # Parse properties JSON if needed
    p = d.get("properties", {})
    if isinstance(p, str):
        try:
            d["properties"] = json.loads(p)
        except (json.JSONDecodeError, TypeError):
            pass
    # Parse datetime fields
    for ts_field in ("created_at", "updated_at"):
        val = d.get(ts_field)
        if isinstance(val, str) and val:
            try:
                d[ts_field] = datetime.fromisoformat(val)
            except ValueError:
                pass
    return GraphNode(d)


async def resolve_person(db, org_id: UUID, identifiers: dict) -> GraphNode:
    """Given identifiers like {"email": "...", "github_username": "...", "slack_id": "...", "name": "..."},
    find or create a canonical Person entity in FalkorDB.

    Delegates to find_person() for the lookup, then creates if no match found.
    """
    entity = await find_person(db, org_id, identifiers)
    if entity is not None:
        return await _enrich_entity(db, entity, identifiers, org_id)

    # No match found - create a new Person entity via FalkorDB
    email = identifiers.get("email")
    github_username = identifiers.get("github_username")
    slack_id = identifiers.get("slack_id")
    name = identifiers.get("name", "")

    source_ids: dict[str, str] = {}
    if email:
        source_ids["email"] = email
    if github_username:
        source_ids["github_username"] = github_username
    if slack_id:
        source_ids["slack_id"] = slack_id

    return await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PERSON,
            source=SourceType.MANUAL,
            source_ids=source_ids,
            canonical_name=name or email or github_username or "Unknown",
            properties={"resolved_from": identifiers},
        ),
    )


async def merge_entities(
    db: AsyncSession,
    primary_id: UUID,
    duplicate_id: UUID,
    *,
    org_id: UUID | None = None,
) -> GraphNode:
    """Merge duplicate into primary: combine source_ids, re-point edges, mark duplicate.

    Graph data (entities, edges) is updated in FalkorDB.
    Relational data (OrgMember, PersonResolution, LinkSuggestion) is updated in PostgreSQL.
    """
    # Resolve org_id from primary entity if not provided
    if org_id is None:
        # Try all org graphs - caller should provide org_id for efficiency
        primary = None
        duplicate = None
    else:
        primary = await get_entity(db, primary_id, org_id=org_id)
        duplicate = await get_entity(db, duplicate_id, org_id=org_id)

    if primary is None or duplicate is None:
        raise ValueError("Both primary and duplicate entities must exist")

    graph = await get_org_graph(org_id)
    now_iso = _utcnow().isoformat()

    # Merge source_ids (additive)
    p_sids = primary.source_ids if isinstance(primary.source_ids, dict) else {}
    d_sids = duplicate.source_ids if isinstance(duplicate.source_ids, dict) else {}
    merged_ids = {**p_sids, **d_sids}

    # Store duplicate's properties under a namespaced key
    p_props = primary.properties if isinstance(primary.properties, dict) else {}
    d_props = duplicate.properties if isinstance(duplicate.properties, dict) else {}
    d_source = duplicate.source if isinstance(duplicate.source, str) else duplicate.source
    connector_data = dict(p_props.get("_connector_data", {}))
    connector_data[d_source] = d_props
    merged_props = {**p_props, "_connector_data": connector_data}

    # Update primary in FalkorDB
    await graph.query(
        "MATCH (n:Entity {id: $id}) SET n.source_ids = $sids, n.properties = $props, n.updated_at = $now RETURN n",
        {
            "id": str(primary_id),
            "sids": json.dumps(merged_ids),
            "props": json.dumps(merged_props),
            "now": now_iso,
        },
    )

    # Re-point edges from the duplicate to the primary in FalkorDB
    dup_edges = await get_edges(db, duplicate_id, org_id=org_id)

    for edge in dup_edges:
        edge_from = str(edge.from_entity_id)
        edge_to = str(edge.to_entity_id)
        str_dup = str(duplicate_id)
        str_primary = str(primary_id)

        new_from = str_primary if edge_from == str_dup else edge_from
        new_to = str_primary if edge_to == str_dup else edge_to

        # Skip self-loops
        if new_from == new_to:
            if hasattr(edge, "id") and edge.id:
                await delete_edge_by_id(db, UUID(edge.id) if isinstance(edge.id, str) else edge.id, org_id=org_id)
            continue

        # Check for conflict
        edge_type = edge.type
        from_uuid = UUID(new_from) if isinstance(new_from, str) else new_from
        to_uuid = UUID(new_to) if isinstance(new_to, str) else new_to
        conflict = await get_edge_by_triple(db, from_uuid, to_uuid, edge_type, org_id=org_id)

        if conflict is not None:
            # Primary already has this edge - delete the duplicate's
            if hasattr(edge, "id") and edge.id:
                await delete_edge_by_id(db, UUID(edge.id) if isinstance(edge.id, str) else edge.id, org_id=org_id)
        else:
            # Re-point the edge via delete + recreate
            if hasattr(edge, "id") and edge.id:
                await delete_edge_by_id(db, UUID(edge.id) if isinstance(edge.id, str) else edge.id, org_id=org_id)
            from src.graph.falkor_repository import upsert_edge
            from src.shared.types import EdgeCreate

            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=from_uuid,
                    to_entity_id=to_uuid,
                    type=edge_type,
                    evidence=edge.get("evidence") or [],
                ),
            )

    # ── PostgreSQL relational updates ──

    # Re-point OrgMember.person_entity_id
    await db.execute(
        update(OrgMember).where(OrgMember.person_entity_id == duplicate_id).values(person_entity_id=primary_id)
    )

    # Mark pending person resolutions as merged
    await db.execute(
        update(PersonResolution)
        .where(
            or_(
                PersonResolution.candidate_entity_id == duplicate_id,
                PersonResolution.match_entity_id == duplicate_id,
            ),
            PersonResolution.status == PersonResolutionStatus.PENDING,
        )
        .values(status=PersonResolutionStatus.MERGED, resolved_at=_utcnow())
    )

    # Delete link suggestions referencing the duplicate
    await db.execute(
        delete(LinkSuggestion).where(
            or_(
                LinkSuggestion.source_entity_id == duplicate_id,
                LinkSuggestion.target_entity_id == duplicate_id,
            )
        )
    )

    # Mark the duplicate as merged in FalkorDB. Also clear source_key so future
    # upsert_entity MERGE lookups can't re-match this stub and resurrect it.
    await graph.query(
        "MATCH (n:Entity {id: $id}) SET n.merged_into = $mid, n.updated_at = $now, n.source_key = NULL RETURN n",
        {"id": str(duplicate_id), "mid": str(primary_id), "now": now_iso},
    )

    # Return updated primary
    return await get_entity(db, primary_id, org_id=org_id)


async def find_similar_persons(db, org_id: UUID, name: str, email: str | None = None) -> list[GraphNode]:
    """Find potential duplicate Person entities for a resolution UI."""
    if not name and not email:
        return []

    graph = await get_org_graph(org_id)
    result = await graph.query("MATCH (n:Entity) WHERE n.type = 'person' RETURN n")

    matches = []
    name_lower = name.strip().lower() if name else ""
    email_lower = email.lower() if email else ""

    for row in result.result_set:
        props = dict(row[0].properties) if hasattr(row[0], "properties") else dict(row[0])

        # Skip merged entities
        if props.get("merged_into") is not None:
            continue

        sids = props.get("source_ids", {})
        if isinstance(sids, str):
            try:
                sids = json.loads(sids)
            except (json.JSONDecodeError, TypeError):
                sids = {}

        matched = False

        # Fuzzy name match: case-insensitive contains
        if name_lower:
            cname = (props.get("canonical_name") or "").lower()
            if name_lower in cname:
                matched = True

        # Email match in source_ids
        if email_lower:
            if sids.get("email", "").lower() == email_lower:
                matched = True

        if matched:
            matches.append(_props_to_graphnode(props, sids))

    return matches


_ENRICH_KEYS = (
    "email",
    "github_username",
    "github",
    "github_id",
    "slack_id",
    "slack",
    "linear",
    "linear_id",
    "linear_identifier",
    "notion_page_id",
    "github_repo_id",
    "github_issue_id",
    "github_pr_id",
    "sha",
)


async def _enrich_entity(
    db,
    entity: GraphNode,
    identifiers: dict,
    org_id: UUID,
    *,
    connector_source: SourceType | None = None,
    connector_properties: dict | None = None,
) -> GraphNode:
    """Enrich an existing entity with additional identifiers (and optional connector props).

    If connector_source + connector_properties are provided, the connector's
    properties are stashed under properties._connector_data[<source>] so every
    connector's view of the entity is preserved.
    """
    updated = False
    existing_sids = entity.get("source_ids") if hasattr(entity, "get") else getattr(entity, "source_ids", None)
    source_ids = dict(existing_sids) if existing_sids else {}

    for key in _ENRICH_KEYS:
        value = identifiers.get(key)
        if value and key not in source_ids:
            source_ids[key] = value
            updated = True

    # Also absorb any extra keys from identifiers we didn't whitelist.
    for key, value in identifiers.items():
        if key == "name":
            continue
        if value and key not in source_ids:
            source_ids[key] = value
            updated = True

    existing_props = entity.get("properties") if hasattr(entity, "get") else getattr(entity, "properties", None)
    properties = dict(existing_props) if existing_props else {}
    props_changed = False
    if connector_source is not None and connector_properties:
        connector_data = dict(properties.get("_connector_data", {}))
        connector_data[connector_source.value] = connector_properties
        properties["_connector_data"] = connector_data
        updated = True
        props_changed = True

    if updated:
        graph = await get_org_graph(org_id)
        now_iso = _utcnow().isoformat()
        if props_changed:
            await graph.query(
                "MATCH (n:Entity {id: $id}) SET n.source_ids = $sids, n.properties = $props, n.updated_at = $now",
                {
                    "id": str(entity.id),
                    "sids": json.dumps(source_ids),
                    "props": json.dumps(properties),
                    "now": now_iso,
                },
            )
        else:
            await graph.query(
                "MATCH (n:Entity {id: $id}) SET n.source_ids = $sids, n.updated_at = $now",
                {
                    "id": str(entity.id),
                    "sids": json.dumps(source_ids),
                    "now": now_iso,
                },
            )
        entity.source_ids = source_ids
        if props_changed:
            entity.properties = properties
        entity.updated_at = _utcnow()

    return entity


async def resolve_or_create_person(
    db,
    org_id: UUID,
    source: SourceType,
    source_ids: dict[str, str],
    canonical_name: str,
    properties: dict,
) -> GraphNode:
    """Connector-facing person resolution wrapper.

    Thin wrapper over resolve_or_create_entity() preserved for call-site back-compat.
    """
    return await resolve_or_create_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PERSON,
            source=source,
            source_ids=source_ids,
            canonical_name=canonical_name,
            properties=properties,
        ),
    )


def _person_identifiers(entity: EntityCreate) -> dict:
    """Extract cross-source match keys for a PERSON EntityCreate."""
    identifiers: dict[str, str] = {}
    source_ids = entity.source_ids or {}
    properties = entity.properties or {}

    email = source_ids.get("email") or properties.get("email")
    if email:
        identifiers["email"] = email.lower()

    github = source_ids.get("github") or source_ids.get("github_username") or properties.get("login")
    if github:
        identifiers["github_username"] = github

    github_id = source_ids.get("github_id")
    if github_id:
        identifiers["github_id"] = str(github_id)

    slack_id = source_ids.get("slack_id") or source_ids.get("slack")
    if slack_id:
        identifiers["slack_id"] = slack_id

    name = entity.canonical_name or properties.get("display_name") or properties.get("real_name")
    if name:
        identifiers["name"] = name

    for key, value in source_ids.items():
        if key not in identifiers and value:
            identifiers[key] = value

    return identifiers


_TYPE_MATCH_KEYS: dict[EntityType, tuple[str, ...]] = {
    EntityType.TASK: (
        "linear_id",
        "linear",
        "linear_identifier",
        "github_issue_id",
        "external_id",
    ),
    EntityType.PROJECT: (
        "linear_project_id",
        "github_repo_id",
        "notion_page_id",
    ),
    EntityType.GOAL: (
        "linear_project_id",
        "notion_page_id",
    ),
    EntityType.COMMIT_PR: (
        "github_id",
        "github_pr_id",
        "sha",
    ),
}


async def _find_by_source_ids(
    db,
    org_id: UUID,
    entity_type: EntityType,
    source_ids: dict[str, str],
) -> GraphNode | None:
    """Find a non-merged entity of the given type whose source_ids match any key/value pair."""
    if not source_ids:
        return None

    graph = await get_org_graph(org_id)
    result = await graph.query(
        "MATCH (n:Entity) WHERE n.type = $etype AND n.merged_into IS NULL RETURN n",
        {"etype": entity_type.value},
    )
    if not result.result_set:
        return None

    for row in result.result_set:
        props = dict(row[0].properties) if hasattr(row[0], "properties") else dict(row[0])
        sids = props.get("source_ids", {})
        if isinstance(sids, str):
            try:
                sids = json.loads(sids)
            except (json.JSONDecodeError, TypeError):
                sids = {}
        for key, value in source_ids.items():
            if not value:
                continue
            if sids.get(key) == value:
                return _props_to_graphnode(props, sids)
    return None


async def resolve_or_create_entity(
    db,
    entity: EntityCreate,
    *,
    match_keys: list[str] | None = None,
) -> GraphNode:
    """Type-agnostic entity resolver used by all connectors.

    1. Build candidate match keys from the EntityCreate (type-specific rules unless
       ``match_keys`` is provided explicitly).
    2. Look up existing entities in the same org that match any of the keys. Merged
       entities are excluded.
    3. If matched: enrich with new source_ids + connector properties; return existing.
    4. If unmatched: fall through to upsert_entity() which creates within the
       connector's source scope.
    """
    org_id = entity.org_id

    if entity.type == EntityType.PERSON:
        identifiers = _person_identifiers(entity)
        has_strong = any(k in identifiers for k in ("email", "github_username", "github_id", "slack_id"))
        if has_strong:
            existing = await find_person(db, org_id, identifiers)
            if existing is not None:
                return await _enrich_entity(
                    db,
                    existing,
                    identifiers,
                    org_id,
                    connector_source=entity.source,
                    connector_properties=entity.properties,
                )
        return await upsert_entity(db, entity)

    keys = match_keys or list(_TYPE_MATCH_KEYS.get(entity.type, ()))
    if keys:
        match_sids = {k: entity.source_ids.get(k) for k in keys if entity.source_ids and entity.source_ids.get(k)}
        if match_sids:
            existing = await _find_by_source_ids(db, org_id, entity.type, match_sids)
            if existing is not None:
                identifiers = dict(entity.source_ids or {})
                return await _enrich_entity(
                    db,
                    existing,
                    identifiers,
                    org_id,
                    connector_source=entity.source,
                    connector_properties=entity.properties,
                )

    return await upsert_entity(db, entity)
