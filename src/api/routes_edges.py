"""Generic edge CRUD routes for the context graph."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.schemas import (
    EdgeCreateRequest,
    EdgeDeleteRequest,
    EdgeListResponse,
    EdgeResponse,
    ErrorResponse,
)
from src.graph import get_edge_by_triple, get_entity, list_edges, upsert_edge
from src.shared.models import Organization
from src.shared.types import EdgeCreate

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/orgs/{org_id}/edges",
    tags=["edges"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


async def _validate_entity_in_org(db: AsyncSession, entity_id: UUID, org_id: UUID, label: str = "Entity"):
    """Verify an entity exists and belongs to the given org. Raise 400 if not."""
    entity = await get_entity(db, entity_id)
    if not entity or entity.org_id != org_id:
        raise HTTPException(
            status_code=400,
            detail=f"{label} {entity_id} not found in org {org_id}",
        )
    return entity


# ── Routes ────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=EdgeResponse,
    status_code=201,
    summary="Create edge",
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def create_edge(
    req: EdgeCreateRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Create an edge between two entities.

    Validates:
    - Both entities exist and belong to the specified org.
    - from_entity_id != to_entity_id (no self-loops).

    If an edge with the same (from, to, type) triple already exists,
    it is updated (weight refreshed, last_active_at bumped) via upsert.
    """
    if req.from_entity_id == req.to_entity_id:
        raise HTTPException(
            status_code=400,
            detail="Cannot create an edge from an entity to itself",
        )

    await _validate_entity_in_org(db, req.from_entity_id, org_id, label="Source entity")
    await _validate_entity_in_org(db, req.to_entity_id, org_id, label="Target entity")

    edge = await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=req.from_entity_id,
            to_entity_id=req.to_entity_id,
            type=req.type,
            weight=req.weight,
            confidence=1.0,  # Manual edges are always confirmed
            evidence=[{"source": "manual_api"}],
        ),
    )

    # Trigger reactive handlers (e.g. task transitions for SHIPS_TO edges)
    from src.events import EdgeCreated, bus

    await bus.emit(
        EdgeCreated(
            db=db,
            org_id=org_id,
            from_entity_id=req.from_entity_id,
            to_entity_id=req.to_entity_id,
            edge_type=req.type,
            skip_auto_transition=req.skip_auto_transition,
        )
    )

    await db.commit()
    return EdgeResponse.model_validate(edge)


@router.delete(
    "",
    status_code=204,
    summary="Delete edge",
    responses={404: {"model": ErrorResponse}},
)
async def delete_edge(
    req: EdgeDeleteRequest,
    org_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
):
    """Delete an edge by its (from_entity_id, to_entity_id, type) triple.

    Returns 404 if no matching edge exists.
    """
    edge = await get_edge_by_triple(db, req.from_entity_id, req.to_entity_id, req.type)
    if not edge or edge.org_id != org_id:
        raise HTTPException(
            status_code=404,
            detail=(f"Edge not found: ({req.from_entity_id} -> {req.to_entity_id}, type={req.type.value})"),
        )

    await db.delete(edge)
    await db.commit()
    return None


@router.get(
    "/entity/{entity_id}",
    response_model=EdgeListResponse,
    summary="Get edges for entity",
    responses={400: {"model": ErrorResponse}},
)
async def get_edges_for_entity(
    org_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    direction: str = Query("both", description="Filter direction: outgoing, incoming, or both"),
    db: AsyncSession = Depends(get_db),
):
    """Get all edges for an entity, optionally filtered by direction.

    Direction semantics:
    - outgoing: edges where entity is the source (from_entity_id = entity_id)
    - incoming: edges where entity is the target (to_entity_id = entity_id)
    - both: all edges involving the entity (default)
    """
    # Validate entity exists in the org
    await _validate_entity_in_org(db, entity_id, org_id)

    # Validate direction parameter
    if direction not in ("outgoing", "incoming", "both"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid direction: {direction}. Must be 'outgoing', 'incoming', or 'both'.",
        )

    edges = await list_edges(db, org_id=org_id, entity_id=entity_id, direction=direction)

    return EdgeListResponse(items=[EdgeResponse.model_validate(e) for e in edges])
