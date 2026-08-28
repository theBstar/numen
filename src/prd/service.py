"""Core CRUD service for PRD documents and folders.

Entities live in FalkorDB (graph DB). Rich content blocks, versions,
comments, and media live in PostgreSQL. All queries scoped by org_id.
"""

from __future__ import annotations

import json
import logging
import uuid as _uuid
from datetime import date as date_type
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_repository import (
    delete_edge_by_id,
    get_edges,
    get_entity,
    list_edges,
    list_entities,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.prd.blocks import create_version
from src.prd.deletion import cascade_archive_prd
from src.prd.schemas import (
    PrdCreate,
    PrdMoveRequest,
    PrdResponse,
    PrdTreeNode,
    PrdUpdate,
)
from src.shared.models import OrgMember, PrdBlock, PrdComment, PrdVersion
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    PrdNodeType,
    PrdStatus,
    Priority,
    SourceType,
)

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────


def _entity_to_prd_response(
    entity,
    *,
    parent_id: UUID | None = None,
    block_count: int = 0,
    comment_count: int = 0,
    version: int = 0,
    owner_name: str | None = None,
) -> PrdResponse:
    """Convert a FalkorDB GraphNode to a PrdResponse."""
    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    entity_id = entity.id
    if isinstance(entity_id, str):
        entity_id = UUID(entity_id)

    owner_member_id_raw = props.get("owner_member_id")
    owner_member_id = None
    if owner_member_id_raw:
        try:
            owner_member_id = UUID(str(owner_member_id_raw))
        except (ValueError, TypeError):
            pass

    target_date_raw = props.get("target_date")
    target_date = None
    if target_date_raw:
        if isinstance(target_date_raw, date_type):
            target_date = target_date_raw
        elif isinstance(target_date_raw, str):
            try:
                target_date = date_type.fromisoformat(target_date_raw)
            except ValueError:
                pass

    return PrdResponse(
        id=entity_id,
        title=entity.canonical_name,
        node_type=PrdNodeType(props.get("node_type", "document")),
        status=PrdStatus(props.get("prd_status", "draft")),
        owner=owner_name,
        owner_member_id=owner_member_id,
        description=props.get("description"),
        priority=Priority(props.get("priority", "medium")),
        target_date=target_date,
        tags=props.get("tags", []) or [],
        cover_image_url=props.get("cover_image_url"),
        parent_id=parent_id,
        block_count=block_count,
        comment_count=comment_count,
        version=version,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


async def _get_owner_name(db: AsyncSession, member_id: UUID | None) -> str | None:
    """Look up display name for an org member."""
    if member_id is None:
        return None
    result = await db.execute(select(OrgMember.display_name).where(OrgMember.id == member_id))
    row = result.scalar_one_or_none()
    return row


async def _get_block_count(db: AsyncSession, entity_id: UUID) -> int:
    """Count blocks for a PRD entity."""
    result = await db.execute(
        select(func.count(PrdBlock.id)).where(PrdBlock.entity_id == entity_id)
    )
    return result.scalar_one() or 0


async def _get_comment_count(db: AsyncSession, entity_id: UUID) -> int:
    """Count comments for a PRD entity."""
    result = await db.execute(
        select(func.count(PrdComment.id)).where(PrdComment.entity_id == entity_id)
    )
    return result.scalar_one() or 0


async def _get_latest_version(db: AsyncSession, entity_id: UUID) -> int:
    """Get the latest version number for a PRD entity."""
    result = await db.execute(
        select(func.max(PrdVersion.version)).where(PrdVersion.entity_id == entity_id)
    )
    return result.scalar_one() or 0


async def _get_parent_id(db: AsyncSession, org_id: UUID, entity_id: UUID) -> UUID | None:
    """Find parent entity via incoming CONTAINS edge."""
    edges = await get_edges(
        db,
        entity_id,
        edge_types=[EdgeType.CONTAINS],
        direction="incoming",
        org_id=org_id,
    )
    if edges:
        from_id = edges[0].from_entity_id
        if isinstance(from_id, str):
            return UUID(from_id)
        return from_id
    return None


# ── CRUD operations ───────────────────────────────────────────────────


async def create_prd(
    db: AsyncSession, org_id: UUID, member_id: UUID, data: PrdCreate
) -> PrdResponse:
    """Create a new PRD document or folder entity in FalkorDB."""
    properties = {
        "prd_status": PrdStatus.DRAFT.value,
        "node_type": data.node_type.value,
        "description": data.description,
        "owner_member_id": str(member_id),
        "priority": data.priority.value,
        "target_date": data.target_date.isoformat() if data.target_date else None,
        "tags": data.tags,
        "cover_image_url": None,
        "position": data.position,
    }

    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.DOCUMENT,
            source=SourceType.MANUAL,
            source_ids={"prd": str(_uuid.uuid4())},
            canonical_name=data.title,
            properties=properties,
        ),
    )

    entity_id = UUID(str(entity.id))

    # Create CONTAINS edge from parent if specified
    if data.parent_id is not None:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=data.parent_id,
                to_entity_id=entity_id,
                type=EdgeType.CONTAINS,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "prd_create", "position": data.position}],
            ),
        )

    # Create OWNS edge from member's person entity (if available)
    member_result = await db.execute(
        select(OrgMember.person_entity_id, OrgMember.display_name).where(OrgMember.id == member_id)
    )
    member_row = member_result.first()
    owner_name = None
    if member_row:
        owner_name = member_row.display_name
        if member_row.person_entity_id:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=member_row.person_entity_id,
                    to_entity_id=entity_id,
                    type=EdgeType.OWNS,
                    weight=1.0,
                    confidence=1.0,
                    evidence=[{"source": "prd_create"}],
                ),
            )

    return _entity_to_prd_response(
        entity,
        parent_id=data.parent_id,
        block_count=0,
        comment_count=0,
        version=0,
        owner_name=owner_name,
    )


async def get_prd(db: AsyncSession, org_id: UUID, entity_id: UUID) -> PrdResponse:
    """Fetch a single PRD by entity ID with block/comment counts."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="PRD not found")

    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    if props.get("node_type") not in (
        PrdNodeType.DOCUMENT.value,
        PrdNodeType.FOLDER.value,
        PrdNodeType.IMAGE.value,
    ):
        raise HTTPException(status_code=404, detail="PRD not found")

    block_count = await _get_block_count(db, entity_id)
    comment_count = await _get_comment_count(db, entity_id)
    version = await _get_latest_version(db, entity_id)
    parent_id = await _get_parent_id(db, org_id, entity_id)

    owner_member_id_raw = props.get("owner_member_id")
    owner_name = None
    if owner_member_id_raw:
        try:
            owner_name = await _get_owner_name(db, UUID(str(owner_member_id_raw)))
        except (ValueError, TypeError):
            pass

    return _entity_to_prd_response(
        entity,
        parent_id=parent_id,
        block_count=block_count,
        comment_count=comment_count,
        version=version,
        owner_name=owner_name,
    )


async def list_prds(
    db: AsyncSession,
    org_id: UUID,
    status: PrdStatus | None = None,
    owner_member_id: UUID | None = None,
    search: str | None = None,
    node_type: PrdNodeType | None = None,
) -> list[PrdResponse]:
    """List PRD documents with optional filters."""
    # Fetch all DOCUMENT entities from FalkorDB
    entities = await list_entities(
        db,
        org_id,
        entity_type=EntityType.DOCUMENT,
        search=search,
        limit=500,
    )

    results: list[PrdResponse] = []
    for entity in entities:
        props = entity.properties
        if isinstance(props, str):
            props = json.loads(props)

        # Only include entities that have PRD node_type
        entity_node_type = props.get("node_type")
        if entity_node_type not in (
            PrdNodeType.DOCUMENT.value,
            PrdNodeType.FOLDER.value,
            PrdNodeType.IMAGE.value,
        ):
            continue

        # Exclude archived/deleted PRDs unless explicitly filtering for them
        if status is None and props.get("prd_status") == PrdStatus.ARCHIVED.value:
            continue

        # Apply status filter
        if status is not None and props.get("prd_status") != status.value:
            continue

        # Apply node_type filter
        if node_type is not None and entity_node_type != node_type.value:
            continue

        # Apply owner filter
        if owner_member_id is not None:
            if props.get("owner_member_id") != str(owner_member_id):
                continue

        eid = UUID(str(entity.id))
        block_count = await _get_block_count(db, eid)
        comment_count = await _get_comment_count(db, eid)
        version = await _get_latest_version(db, eid)
        parent_id = await _get_parent_id(db, org_id, eid)

        owner_name = None
        owner_mid = props.get("owner_member_id")
        if owner_mid:
            try:
                owner_name = await _get_owner_name(db, UUID(str(owner_mid)))
            except (ValueError, TypeError):
                pass

        results.append(
            _entity_to_prd_response(
                entity,
                parent_id=parent_id,
                block_count=block_count,
                comment_count=comment_count,
                version=version,
                owner_name=owner_name,
            )
        )

    return results


async def update_prd(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    data: PrdUpdate,
) -> PrdResponse:
    """Update a PRD entity's properties in FalkorDB."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="PRD not found")

    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    old_status = props.get("prd_status")

    # Build updated properties dict
    updated_props = dict(props)
    if data.title is not None:
        pass  # canonical_name handled separately
    if data.status is not None:
        updated_props["prd_status"] = data.status.value
    if data.description is not None:
        updated_props["description"] = data.description
    if data.priority is not None:
        updated_props["priority"] = data.priority.value
    if data.target_date is not None:
        updated_props["target_date"] = data.target_date.isoformat()
    if data.tags is not None:
        updated_props["tags"] = data.tags
    if data.cover_image_url is not None:
        updated_props["cover_image_url"] = data.cover_image_url
    if data.owner_member_id is not None:
        updated_props["owner_member_id"] = str(data.owner_member_id)

    await update_entity(
        db,
        entity_id,
        org_id=org_id,
        canonical_name=data.title,
        properties=updated_props,
        merge_properties=False,
    )

    # If status changed, create a version snapshot
    if data.status is not None and data.status.value != old_status:
        await create_version(
            db,
            org_id,
            entity_id,
            member_id,
            status=data.status.value,
            message=f"Status changed from {old_status} to {data.status.value}",
        )

    return await get_prd(db, org_id, entity_id)


async def delete_prd(db: AsyncSession, org_id: UUID, entity_id: UUID) -> None:
    """Soft-delete a PRD: archive the entity and cascade-clean derived artifacts."""
    await cascade_archive_prd(db, org_id, entity_id)


async def get_prd_tree(db: AsyncSession, org_id: UUID) -> list[PrdTreeNode]:
    """Build the full PRD folder tree for an org.

    Returns root-level nodes (no parent) with recursively nested children.
    """
    # Fetch all DOCUMENT entities
    entities = await list_entities(
        db,
        org_id,
        entity_type=EntityType.DOCUMENT,
        limit=1000,
    )

    # Fetch all CONTAINS edges to determine parent-child relationships
    contains_edges = await list_edges(
        db,
        org_id=org_id,
        edge_type=EdgeType.CONTAINS,
    )

    # Build child -> parent mapping
    child_to_parent: dict[str, str] = {}
    for edge in contains_edges:
        from_id = str(edge.from_entity_id)
        to_id = str(edge.to_entity_id)
        child_to_parent[to_id] = from_id

    # Build flat node mapping
    nodes: dict[str, PrdTreeNode] = {}
    for entity in entities:
        props = entity.properties
        if isinstance(props, str):
            props = json.loads(props)

        entity_node_type = props.get("node_type")
        if entity_node_type not in (
            PrdNodeType.DOCUMENT.value,
            PrdNodeType.FOLDER.value,
            PrdNodeType.IMAGE.value,
        ):
            continue

        # Exclude archived from tree
        if props.get("prd_status") == PrdStatus.ARCHIVED.value:
            continue

        eid = str(entity.id)
        parent_str = child_to_parent.get(eid)
        parent_uuid = UUID(parent_str) if parent_str else None

        nodes[eid] = PrdTreeNode(
            id=UUID(eid),
            title=entity.canonical_name,
            node_type=PrdNodeType(entity_node_type),
            status=PrdStatus(props.get("prd_status", "draft")),
            parent_id=parent_uuid,
            position=float(props.get("position", 0)),
            children=[],
        )

    # Build tree by attaching children to parents
    root_nodes: list[PrdTreeNode] = []
    for eid, node in nodes.items():
        parent_str = child_to_parent.get(eid)
        if parent_str and parent_str in nodes:
            nodes[parent_str].children.append(node)
        else:
            root_nodes.append(node)

    # Sort children by position at each level
    def _sort_children(node: PrdTreeNode) -> None:
        node.children.sort(key=lambda n: n.position)
        for child in node.children:
            _sort_children(child)

    root_nodes.sort(key=lambda n: n.position)
    for root in root_nodes:
        _sort_children(root)

    return root_nodes


async def move_prd(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    data: PrdMoveRequest,
) -> None:
    """Move a PRD to a new parent (or root) and update its position."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="PRD not found")

    # Remove old CONTAINS edge (where this entity is the child)
    old_edges = await get_edges(
        db,
        entity_id,
        edge_types=[EdgeType.CONTAINS],
        direction="incoming",
        org_id=org_id,
    )
    for edge in old_edges:
        edge_id = edge.id
        if isinstance(edge_id, str):
            edge_id = UUID(edge_id)
        await delete_edge_by_id(db, edge_id, org_id=org_id)

    # Create new CONTAINS edge if parent_id is provided
    if data.parent_id is not None:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=data.parent_id,
                to_entity_id=entity_id,
                type=EdgeType.CONTAINS,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "prd_move", "position": data.position}],
            ),
        )

    # Update position in entity properties
    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    props["position"] = data.position

    await update_entity(
        db,
        entity_id,
        org_id=org_id,
        properties=props,
        merge_properties=False,
    )
