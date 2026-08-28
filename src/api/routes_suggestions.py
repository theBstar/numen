"""Link suggestion routes."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    EntityResponse,
    LinkSuggestionCountResponse,
    LinkSuggestionListResponse,
    LinkSuggestionResponse,
)
from src.graph import (
    get_entity as graph_get_entity,
)
from src.graph import (
    upsert_edge,
)
from src.shared.models import LinkSuggestion, OrgMember
from src.shared.types import EdgeCreate

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["suggestions"])


@router.get("/orgs/{org_id}/suggestions", response_model=LinkSuggestionListResponse)
async def list_link_suggestions(
    org_id: UUID = Path(...),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List AI-suggested entity links, optionally filtered by status."""
    query = select(LinkSuggestion).where(LinkSuggestion.org_id == org_id)
    if status:
        query = query.where(LinkSuggestion.status == status)
    query = query.order_by(LinkSuggestion.confidence.desc()).limit(limit)

    result = await db.execute(query)
    suggestions = list(result.scalars().all())

    items = []
    for s in suggestions:
        source = await graph_get_entity(db, s.source_entity_id, org_id=org_id)
        target = await graph_get_entity(db, s.target_entity_id, org_id=org_id)
        if not source or not target:
            continue
        items.append(
            LinkSuggestionResponse(
                id=s.id,
                source_entity=EntityResponse.model_validate(source),
                target_entity=EntityResponse.model_validate(target),
                edge_type=s.edge_type,
                confidence=s.confidence,
                reasoning=s.reasoning,
                status=s.status,
                created_at=s.created_at,
            )
        )

    return LinkSuggestionListResponse(items=items)


@router.get("/orgs/{org_id}/suggestions/count", response_model=LinkSuggestionCountResponse)
async def count_link_suggestions(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Count pending link suggestions for badge display."""
    result = await db.execute(
        select(func.count())
        .select_from(LinkSuggestion)
        .where(
            LinkSuggestion.org_id == org_id,
            LinkSuggestion.status == "pending",
        )
    )
    count = result.scalar() or 0
    return LinkSuggestionCountResponse(pending=count)


@router.post("/orgs/{org_id}/suggestions/{suggestion_id}/accept", response_model=LinkSuggestionResponse)
async def accept_link_suggestion(
    org_id: UUID = Path(...),
    suggestion_id: UUID = Path(...),
    skip_auto_transition: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Accept a suggestion - creates the actual edge."""
    suggestion = await db.get(LinkSuggestion, suggestion_id)
    if not suggestion or suggestion.org_id != org_id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != "pending":
        raise HTTPException(status_code=400, detail=f"Suggestion already {suggestion.status}")

    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=suggestion.source_entity_id,
            to_entity_id=suggestion.target_entity_id,
            type=suggestion.edge_type,
            weight=1.0,
            confidence=suggestion.confidence,
            evidence=[{"source": "ai_suggestion", "reasoning": suggestion.reasoning}],
        ),
    )

    # Trigger task transitions if a SHIPS_TO edge connects a merged PR to a task
    from src.events import EdgeCreated, bus

    await bus.emit(
        EdgeCreated(
            db=db,
            org_id=org_id,
            from_entity_id=suggestion.source_entity_id,
            to_entity_id=suggestion.target_entity_id,
            edge_type=suggestion.edge_type,
            skip_auto_transition=skip_auto_transition,
        )
    )

    suggestion.status = "accepted"
    await db.commit()

    source = await graph_get_entity(db, suggestion.source_entity_id, org_id=org_id)
    target = await graph_get_entity(db, suggestion.target_entity_id, org_id=org_id)
    return LinkSuggestionResponse(
        id=suggestion.id,
        source_entity=EntityResponse.model_validate(source),
        target_entity=EntityResponse.model_validate(target),
        edge_type=suggestion.edge_type,
        confidence=suggestion.confidence,
        reasoning=suggestion.reasoning,
        status=suggestion.status,
        created_at=suggestion.created_at,
    )


@router.post("/orgs/{org_id}/suggestions/{suggestion_id}/dismiss", response_model=LinkSuggestionResponse)
async def dismiss_link_suggestion(
    org_id: UUID = Path(...),
    suggestion_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Dismiss a suggestion."""
    suggestion = await db.get(LinkSuggestion, suggestion_id)
    if not suggestion or suggestion.org_id != org_id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != "pending":
        raise HTTPException(status_code=400, detail=f"Suggestion already {suggestion.status}")

    suggestion.status = "dismissed"
    await db.commit()

    source = await graph_get_entity(db, suggestion.source_entity_id, org_id=org_id)
    target = await graph_get_entity(db, suggestion.target_entity_id, org_id=org_id)
    return LinkSuggestionResponse(
        id=suggestion.id,
        source_entity=EntityResponse.model_validate(source),
        target_entity=EntityResponse.model_validate(target),
        edge_type=suggestion.edge_type,
        confidence=suggestion.confidence,
        reasoning=suggestion.reasoning,
        status=suggestion.status,
        created_at=suggestion.created_at,
    )


@router.post("/orgs/{org_id}/suggestions/generate", response_model=LinkSuggestionListResponse)
async def generate_link_suggestions(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Manually trigger AI link suggestion generation."""
    from src.llm.link_suggester import suggest_pr_task_links

    try:
        new_suggestions = await suggest_pr_task_links(db, org_id)
        await db.commit()
    except Exception as exc:
        logger.warning("Link suggestion generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Suggestion generation failed: {exc}")

    items = []
    for s in new_suggestions:
        source = await graph_get_entity(db, s.source_entity_id, org_id=org_id)
        target = await graph_get_entity(db, s.target_entity_id, org_id=org_id)
        if source and target:
            items.append(
                LinkSuggestionResponse(
                    id=s.id,
                    source_entity=EntityResponse.model_validate(source),
                    target_entity=EntityResponse.model_validate(target),
                    edge_type=s.edge_type,
                    confidence=s.confidence,
                    reasoning=s.reasoning,
                    status=s.status,
                    created_at=s.created_at,
                )
            )

    return LinkSuggestionListResponse(items=items)
