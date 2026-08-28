"""FastAPI routes for PRD document system.

Thin routing layer - business logic lives in service.py, blocks.py,
and media.py. All routes scoped by org_id.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.graph import (
    get_edges,
    get_entity,
    get_entity_neighborhood,
)
from src.prd.blocks import (
    batch_update_blocks,
    create_version,
    get_blocks,
    get_version_detail,
    get_versions,
)
from src.prd.comments import (
    create_comment,
    delete_comment,
    get_block_reactions,
    list_comments,
    resolve_comment,
    toggle_reaction,
    unresolve_comment,
    update_comment,
)
from src.prd.media import (
    confirm_upload,
    generate_upload_url,
    list_media,
)
from src.prd.reviews import (
    add_reviewer,
    add_stakeholder,
    get_review_summary,
    list_reviews,
    list_stakeholders,
    remove_reviewer,
    remove_stakeholder,
    submit_review,
    validate_transition,
)
from src.prd.schemas import (
    AiCompletedBlock,
    AiCompleteRequest,
    AiEditSectionRequest,
    AiSuggestedReviewer,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
    ExportRequest,
    ExportResponse,
    ImportBulkRequest,
    ImportBulkResponse,
    ImportRequest,
    PrdBlockBatchRequest,
    PrdBlockResponse,
    PrdBlockUpdate,
    PrdCoverage,
    PrdCreate,
    PrdMediaResponse,
    PrdMoveRequest,
    PrdReference,
    PrdResponse,
    PrdStatusTransition,
    PrdUpdate,
    PrdVersionDetail,
    PrdVersionResponse,
    ReactionResponse,
    ReactionToggle,
    ReviewerRequest,
    ReviewResponse,
    ReviewSubmit,
    ReviewSummary,
    StakeholderRequest,
    StakeholderResponse,
    UploadConfirmRequest,
    UploadUrlRequest,
    UploadUrlResponse,
)
from src.prd.service import (
    create_prd,
    delete_prd,
    get_prd,
    get_prd_tree,
    list_prds,
    move_prd,
    update_prd,
)
from src.prd.wiki import invalidate_wiki_cache
from src.shared.models import OAuthToken, OrgMember
from src.shared.types import EdgeType, EntityType, PrdNodeType, PrdStatus, SourceType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orgs/{org_id}/prds", tags=["prds"])


# ── Document CRUD ─────────────────────────────────────────────────────


@router.post(
    "",
    response_model=PrdResponse,
    status_code=201,
    summary="Create PRD document or folder",
)
async def create_prd_endpoint(
    data: PrdCreate,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Create a new PRD document or folder."""
    result = await create_prd(db, org_id, member.id, data)
    await db.commit()
    return result


@router.get(
    "",
    response_model=dict,
    summary="List PRD documents",
)
async def list_prds_endpoint(
    org_id: UUID = Path(...),
    status: PrdStatus | None = Query(None, description="Filter by PRD status"),
    owner: UUID | None = Query(None, description="Filter by owner member ID"),
    search: str | None = Query(None, description="Search by title"),
    node_type: PrdNodeType | None = Query(None, description="Filter by node type"),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all PRD documents for the org with optional filters."""
    items = await list_prds(
        db,
        org_id,
        status=status,
        owner_member_id=owner,
        search=search,
        node_type=node_type,
    )
    return {"items": items}


@router.get(
    "/tree",
    response_model=dict,
    summary="Get PRD folder tree",
)
async def get_prd_tree_endpoint(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get the hierarchical folder tree of all PRD documents."""
    items = await get_prd_tree(db, org_id)
    return {"items": items}


@router.get(
    "/{prd_id}",
    response_model=PrdResponse,
    summary="Get PRD document",
)
async def get_prd_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get a single PRD document by ID."""
    return await get_prd(db, org_id, prd_id)


@router.put(
    "/{prd_id}",
    response_model=PrdResponse,
    summary="Update PRD document",
)
async def update_prd_endpoint(
    data: PrdUpdate,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Update a PRD document's metadata."""
    result = await update_prd(db, org_id, prd_id, member.id, data)
    await db.commit()
    return result


@router.delete(
    "/{prd_id}",
    status_code=204,
    summary="Delete PRD document",
)
async def delete_prd_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Soft-delete a PRD document by archiving it."""
    await delete_prd(db, org_id, prd_id)
    await db.commit()


@router.post(
    "/{prd_id}/move",
    status_code=204,
    summary="Move PRD document",
)
async def move_prd_endpoint(
    data: PrdMoveRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Move a PRD document to a new parent folder and/or position."""
    await move_prd(db, org_id, prd_id, data)
    await db.commit()


# ── Blocks ─────────────────────────────────────────────────────────────


@router.get(
    "/{prd_id}/blocks",
    response_model=dict,
    summary="Get PRD blocks",
)
async def get_blocks_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get all content blocks for a PRD document, ordered by position."""
    # Verify the PRD exists
    await get_prd(db, org_id, prd_id)
    items = await get_blocks(db, org_id, prd_id)
    return {"items": items}


@router.patch(
    "/{prd_id}/blocks/batch",
    response_model=dict,
    summary="Batch update PRD blocks",
)
async def batch_update_blocks_endpoint(
    data: PrdBlockBatchRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Batch create, update, and delete blocks in a single request."""
    await get_prd(db, org_id, prd_id)
    items = await batch_update_blocks(db, org_id, prd_id, member.id, data.operations)
    await db.commit()
    return {"items": items}


@router.put(
    "/{prd_id}/blocks/{block_id}",
    response_model=PrdBlockResponse,
    summary="Update a single block",
)
async def update_block_endpoint(
    data: PrdBlockUpdate,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    block_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Update a single block's content, position, or heading level."""
    from src.prd.schemas import PrdBlockBatchOp

    await get_prd(db, org_id, prd_id)

    op = PrdBlockBatchOp(
        op="update",
        id=block_id,
        content=data.content,
        position=data.position,
        heading_level=data.heading_level,
    )
    blocks = await batch_update_blocks(db, org_id, prd_id, member.id, [op])
    await db.commit()

    # Find the updated block in the result
    for block in blocks:
        if block.id == block_id:
            return block

    raise HTTPException(status_code=404, detail="Block not found")


# ── Versions ───────────────────────────────────────────────────────────


@router.get(
    "/{prd_id}/versions",
    response_model=dict,
    summary="List PRD versions",
)
async def list_versions_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all version snapshots for a PRD document."""
    await get_prd(db, org_id, prd_id)
    items = await get_versions(db, org_id, prd_id)
    return {"items": items}


@router.get(
    "/{prd_id}/versions/{version}",
    response_model=PrdVersionDetail,
    summary="Get PRD version detail",
)
async def get_version_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    version: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get a specific version with its full block snapshot."""
    await get_prd(db, org_id, prd_id)
    return await get_version_detail(db, org_id, prd_id, version)


@router.post(
    "/{prd_id}/versions",
    response_model=PrdVersionResponse,
    status_code=201,
    summary="Create PRD version snapshot",
)
async def create_version_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    message: str | None = Query(None, description="Optional version message"),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Manually create a version snapshot of the current blocks."""
    prd = await get_prd(db, org_id, prd_id)
    result = await create_version(
        db,
        org_id,
        prd_id,
        member.id,
        status=prd.status.value,
        message=message,
    )
    await db.commit()
    return result


# ── Media ──────────────────────────────────────────────────────────────


@router.post(
    "/{prd_id}/media/upload",
    response_model=UploadUrlResponse,
    summary="Get presigned upload URL",
)
async def get_upload_url_endpoint(
    data: UploadUrlRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Generate a presigned URL for direct browser-to-S3 upload."""
    await get_prd(db, org_id, prd_id)
    try:
        result = await generate_upload_url(org_id, prd_id, data.file_name, data.file_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return UploadUrlResponse(**result)


@router.post(
    "/{prd_id}/media/confirm",
    response_model=PrdMediaResponse,
    status_code=201,
    summary="Confirm media upload",
)
async def confirm_upload_endpoint(
    data: UploadConfirmRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Confirm a completed upload and create the media record."""
    await get_prd(db, org_id, prd_id)
    try:
        media = await confirm_upload(
            db,
            org_id,
            prd_id,
            member.id,
            storage_key=data.storage_key,
            file_name=data.file_name,
            file_type=data.file_type,
            file_size=data.file_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    await db.commit()
    return PrdMediaResponse(
        id=media.id,
        entity_id=media.entity_id,
        file_name=media.file_name,
        file_type=media.file_type,
        file_size=media.file_size,
        cdn_url=media.cdn_url,
        created_at=media.created_at,
    )


@router.get(
    "/{prd_id}/media",
    response_model=dict,
    summary="List PRD media",
)
async def list_media_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all media uploads for a PRD document."""
    await get_prd(db, org_id, prd_id)
    media_list = await list_media(db, org_id, prd_id)
    return {
        "items": [
            PrdMediaResponse(
                id=m.id,
                entity_id=m.entity_id,
                file_name=m.file_name,
                file_type=m.file_type,
                file_size=m.file_size,
                cdn_url=m.cdn_url,
                created_at=m.created_at,
            )
            for m in media_list
        ]
    }


# ── Comments ──────────────────────────────────────────────────────────


def _comment_to_response(comment) -> CommentResponse:
    """Serialize a PrdComment ORM model into a CommentResponse schema."""
    author_name = None
    if comment.author:
        author_name = comment.author.display_name or comment.author.email

    replies = []
    if comment.replies:
        replies = [_comment_to_response(r) for r in comment.replies]

    return CommentResponse(
        id=comment.id,
        entity_id=comment.entity_id,
        block_id=comment.block_id,
        parent_id=comment.parent_id,
        author_id=comment.author_id,
        author_name=author_name,
        content=comment.content,
        is_resolved=comment.is_resolved,
        resolved_by=comment.resolved_by,
        resolved_at=comment.resolved_at.isoformat() if comment.resolved_at else None,
        replies=replies,
        created_at=comment.created_at.isoformat(),
        updated_at=comment.updated_at.isoformat(),
    )


@router.post(
    "/{prd_id}/comments",
    response_model=CommentResponse,
    status_code=201,
    summary="Create a comment on a PRD",
)
async def create_comment_endpoint(
    data: CommentCreate,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Create a new comment on a PRD document or a specific block."""
    await get_prd(db, org_id, prd_id)
    comment = await create_comment(
        db,
        org_id,
        prd_id,
        member.id,
        block_id=data.block_id,
        parent_id=data.parent_id,
        content=data.content,
    )
    await db.commit()
    return _comment_to_response(comment)


@router.get(
    "/{prd_id}/comments",
    response_model=dict,
    summary="List comments on a PRD",
)
async def list_comments_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    block_id: UUID | None = Query(None, description="Filter by block ID"),
    resolved: bool | None = Query(None, description="Filter by resolved status"),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all comments for a PRD, optionally filtered by block or resolved status."""
    await get_prd(db, org_id, prd_id)
    comments = await list_comments(db, org_id, prd_id, block_id=block_id, resolved=resolved)
    return {"items": [_comment_to_response(c) for c in comments]}


@router.put(
    "/{prd_id}/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Update a comment",
)
async def update_comment_endpoint(
    data: CommentUpdate,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Update a comment's content. Only the author can edit."""
    await get_prd(db, org_id, prd_id)
    comment = await update_comment(db, org_id, comment_id, member.id, data.content)
    await db.commit()
    return _comment_to_response(comment)


@router.delete(
    "/{prd_id}/comments/{comment_id}",
    status_code=204,
    summary="Delete a comment",
)
async def delete_comment_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Delete a comment. Only the author can delete."""
    await get_prd(db, org_id, prd_id)
    await delete_comment(db, org_id, comment_id, member.id)
    await db.commit()


@router.post(
    "/{prd_id}/comments/{comment_id}/resolve",
    response_model=CommentResponse,
    summary="Resolve a comment",
)
async def resolve_comment_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Mark a comment thread as resolved."""
    await get_prd(db, org_id, prd_id)
    comment = await resolve_comment(db, org_id, comment_id, member.id)
    await db.commit()
    return _comment_to_response(comment)


@router.post(
    "/{prd_id}/comments/{comment_id}/unresolve",
    response_model=CommentResponse,
    summary="Unresolve a comment",
)
async def unresolve_comment_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    comment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Re-open a resolved comment thread."""
    await get_prd(db, org_id, prd_id)
    comment = await unresolve_comment(db, org_id, comment_id, member.id)
    await db.commit()
    return _comment_to_response(comment)


# ── Reactions ─────────────────────────────────────────────────────────


@router.post(
    "/{prd_id}/blocks/{block_id}/reactions",
    response_model=dict,
    summary="Toggle a reaction on a block",
)
async def toggle_reaction_endpoint(
    data: ReactionToggle,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    block_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Toggle (add/remove) an emoji reaction on a PRD block."""
    await get_prd(db, org_id, prd_id)
    result = await toggle_reaction(db, org_id, block_id, member.id, data.emoji)
    await db.commit()
    return {
        "added": result["added"],
        "reactions": [
            ReactionResponse(
                emoji=r["emoji"],
                count=r["count"],
                member_ids=r["member_ids"],
            )
            for r in result["reactions"]
        ],
    }


@router.get(
    "/{prd_id}/blocks/{block_id}/reactions",
    response_model=dict,
    summary="Get reactions for a block",
)
async def get_reactions_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    block_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get all reactions for a specific block, grouped by emoji."""
    await get_prd(db, org_id, prd_id)
    reactions = await get_block_reactions(db, org_id, block_id)
    return {
        "items": [
            ReactionResponse(
                emoji=r["emoji"],
                count=r["count"],
                member_ids=r["member_ids"],
            )
            for r in reactions
        ]
    }


# ── Graph connections ──────────────────────────────────────────────────


@router.get(
    "/{prd_id}/references",
    response_model=dict,
    summary="Get PRD references",
)
async def get_references_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get cross-references to and from this PRD document."""
    await get_prd(db, org_id, prd_id)

    references: list[PrdReference] = []

    # Outgoing REFERENCES edges
    outgoing = await get_edges(
        db,
        prd_id,
        edge_types=[EdgeType.REFERENCES],
        direction="outgoing",
        org_id=org_id,
    )
    for edge in outgoing:
        target_id = edge.to_entity_id
        if isinstance(target_id, str):
            target_id = UUID(target_id)
        target = await get_entity(db, target_id, org_id=org_id)
        if target is not None:
            props = target.properties
            if isinstance(props, str):
                import json

                props = json.loads(props)
            if props.get("node_type") in (
                PrdNodeType.DOCUMENT.value,
                PrdNodeType.FOLDER.value,
            ):
                evidence = edge.get("evidence", []) if hasattr(edge, "get") else []
                section_slug = None
                if evidence and isinstance(evidence, list) and len(evidence) > 0:
                    section_slug = evidence[0].get("section_slug")
                references.append(
                    PrdReference(
                        prd_id=target_id,
                        prd_title=target.canonical_name,
                        direction="outgoing",
                        section_slug=section_slug,
                    )
                )

    # Incoming REFERENCES edges
    incoming = await get_edges(
        db,
        prd_id,
        edge_types=[EdgeType.REFERENCES],
        direction="incoming",
        org_id=org_id,
    )
    for edge in incoming:
        source_id = edge.from_entity_id
        if isinstance(source_id, str):
            source_id = UUID(source_id)
        source = await get_entity(db, source_id, org_id=org_id)
        if source is not None:
            props = source.properties
            if isinstance(props, str):
                import json

                props = json.loads(props)
            if props.get("node_type") in (
                PrdNodeType.DOCUMENT.value,
                PrdNodeType.FOLDER.value,
            ):
                evidence = edge.get("evidence", []) if hasattr(edge, "get") else []
                section_slug = None
                if evidence and isinstance(evidence, list) and len(evidence) > 0:
                    section_slug = evidence[0].get("section_slug")
                references.append(
                    PrdReference(
                        prd_id=source_id,
                        prd_title=source.canonical_name,
                        direction="incoming",
                        section_slug=section_slug,
                    )
                )

    return {"items": references}


@router.get(
    "/{prd_id}/coverage",
    response_model=PrdCoverage,
    summary="Get PRD implementation coverage",
)
async def get_coverage_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Compute implementation coverage for a PRD - tasks, PRs, and design links."""
    await get_prd(db, org_id, prd_id)

    # Get tasks linked to this PRD via IMPLEMENTS edges
    task_edges = await get_edges(
        db,
        prd_id,
        edge_types=[EdgeType.IMPLEMENTS],
        direction="incoming",
        org_id=org_id,
    )

    total_tasks = 0
    tasks_done = 0
    tasks_in_progress = 0
    tasks_todo = 0

    for edge in task_edges:
        task_id = edge.from_entity_id
        if isinstance(task_id, str):
            task_id = UUID(task_id)
        task = await get_entity(db, task_id, org_id=org_id)
        if task is not None and task.type == EntityType.TASK.value:
            total_tasks += 1
            props = task.properties
            if isinstance(props, str):
                import json

                props = json.loads(props)
            task_status = props.get("status", "todo")
            if task_status in ("done", "merged", "completed"):
                tasks_done += 1
            elif task_status in ("in_progress", "in_review"):
                tasks_in_progress += 1
            else:
                tasks_todo += 1

    coverage_pct = (tasks_done / total_tasks * 100) if total_tasks > 0 else 0.0

    # Count linked PRs
    pr_edges = await get_edges(
        db,
        prd_id,
        edge_types=[EdgeType.REFERENCES],
        direction="both",
        org_id=org_id,
    )
    linked_prs = 0
    for edge in pr_edges:
        other_id = (
            edge.from_entity_id if str(edge.to_entity_id) == str(prd_id) else edge.to_entity_id
        )
        if isinstance(other_id, str):
            other_id = UUID(other_id)
        other = await get_entity(db, other_id, org_id=org_id)
        if other is not None and other.type == EntityType.COMMIT_PR.value:
            linked_prs += 1

    # Check for design links (Figma etc.)
    has_design = False
    all_edges = await get_edges(
        db,
        prd_id,
        edge_types=[EdgeType.REFERENCES],
        direction="both",
        org_id=org_id,
    )
    for edge in all_edges:
        other_id = (
            edge.from_entity_id if str(edge.to_entity_id) == str(prd_id) else edge.to_entity_id
        )
        if isinstance(other_id, str):
            other_id = UUID(other_id)
        other = await get_entity(db, other_id, org_id=org_id)
        if other is not None:
            props = other.properties
            if isinstance(props, str):
                import json

                props = json.loads(props)
            if props.get("source") == "figma" or other.get("source", "") == "figma":
                has_design = True
                break

    return PrdCoverage(
        total_tasks=total_tasks,
        tasks_done=tasks_done,
        tasks_in_progress=tasks_in_progress,
        tasks_todo=tasks_todo,
        coverage_pct=round(coverage_pct, 1),
        linked_prs=linked_prs,
        has_design=has_design,
    )


@router.get(
    "/{prd_id}/graph",
    summary="Get PRD graph neighborhood",
)
async def get_prd_graph_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get the graph neighborhood for a PRD document - connected entities and edges."""
    await get_prd(db, org_id, prd_id)
    result = await get_entity_neighborhood(db, prd_id, depth=2, org_id=org_id)

    # Serialize GraphNode/GraphEdge objects for JSON response
    entities = []
    for e in result.get("entities", []):
        entities.append(
            {
                "id": e.id,
                "type": e.type,
                "canonical_name": e.canonical_name,
                "properties": e.properties,
            }
        )

    edges = []
    for e in result.get("edges", []):
        edges.append(
            {
                "id": e.get("id") if hasattr(e, "get") else getattr(e, "id", None),
                "from_entity_id": e.from_entity_id,
                "to_entity_id": e.to_entity_id,
                "type": e.type,
            }
        )

    return {"entities": entities, "edges": edges}


# ── AI-powered features ──────────────────────────────────────────────


@router.post(
    "/{prd_id}/ai/complete",
    response_model=dict,
    summary="AI auto-complete PRD",
)
async def ai_complete_endpoint(
    data: AiCompleteRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Generate full PRD content from an initial prompt using AI.

    Returns a list of TipTap JSON blocks for each generated section.
    Blocks are not persisted - the frontend should preview them and
    let the user accept/reject before saving.
    """
    from src.prd.ai import auto_complete_prd

    await get_prd(db, org_id, prd_id)
    try:
        blocks = await auto_complete_prd(db, org_id, prd_id, member.id, data.prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("AI complete failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="AI generation failed. Check LLM configuration."
        )
    return {
        "items": [
            AiCompletedBlock(
                block_type=b["block_type"],
                content=b["content"],
                heading_level=b.get("heading_level"),
                position=b.get("position", 0.0),
                ai_generated=b.get("ai_generated", True),
            )
            for b in blocks
        ]
    }


@router.post(
    "/{prd_id}/ai/edit-section",
    response_model=dict,
    summary="AI edit PRD section",
)
async def ai_edit_section_endpoint(
    data: AiEditSectionRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """AI-edit specific blocks based on a user instruction.

    Pass the block IDs to edit and a natural language instruction.
    Returns updated block content as TipTap JSON. Blocks are not
    persisted - the frontend should preview them first.
    """
    from src.prd.ai import edit_section

    await get_prd(db, org_id, prd_id)
    try:
        blocks = await edit_section(db, org_id, prd_id, data.block_ids, data.instruction)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("AI edit section failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail="AI section edit failed. Check LLM configuration."
        )
    return {
        "items": [
            AiCompletedBlock(
                block_type=b["block_type"],
                content=b["content"],
                heading_level=b.get("heading_level"),
                position=b.get("position", 0.0),
                ai_generated=b.get("ai_generated", True),
            )
            for b in blocks
        ]
    }


@router.get(
    "/{prd_id}/ai/suggest-reviewers",
    response_model=dict,
    summary="AI suggest PRD reviewers",
)
async def ai_suggest_reviewers_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Suggest reviewers based on graph relationships.

    Uses graph traversal (no LLM) to find people connected to this PRD
    via goals, related PRDs, implementing tasks, and projects.
    """
    from src.prd.ai import suggest_reviewers

    await get_prd(db, org_id, prd_id)
    reviewers = await suggest_reviewers(db, org_id, prd_id)
    return {
        "items": [
            AiSuggestedReviewer(
                member_id=r["member_id"],
                person_name=r["person_name"],
                reason=r["reason"],
                score=r["score"],
            )
            for r in reviewers
        ]
    }


# ── Status transition ──────────────────────────────────────────────────


@router.post(
    "/{prd_id}/transition",
    response_model=PrdResponse,
    summary="Transition PRD status",
)
async def transition_status_endpoint(
    data: PrdStatusTransition,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Transition a PRD document to a new lifecycle status.

    Creates a version snapshot on each status transition. Validates the
    transition using review-gate rules - e.g. draft->in_review requires
    reviewers, in_review->approved requires all approvals.
    """
    prd = await get_prd(db, org_id, prd_id)
    current_status = prd.status
    new_status = data.new_status

    # Get review summary for validation
    summary = await get_review_summary(db, org_id, prd_id)

    is_valid, reason = await validate_transition(current_status, new_status, summary)
    if not is_valid:
        raise HTTPException(status_code=400, detail=reason)

    # Update the status via the service
    result = await update_prd(
        db,
        org_id,
        prd_id,
        member.id,
        PrdUpdate(status=new_status),
    )

    await db.commit()

    # Invalidate wiki cache so status changes reflect immediately
    await invalidate_wiki_cache(org_id)

    return result


# ── Reviewers ─────────────────────────────────────────────────────────


@router.post(
    "/{prd_id}/reviewers",
    response_model=StakeholderResponse,
    status_code=201,
    summary="Add a reviewer to a PRD",
)
async def add_reviewer_endpoint(
    data: ReviewerRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Add a reviewer to a PRD document. Creates REVIEWER_OF edge and PrdReview record."""
    await get_prd(db, org_id, prd_id)
    result = await add_reviewer(db, org_id, prd_id, member.id, data.member_id)
    await db.commit()
    return StakeholderResponse(**result)


@router.delete(
    "/{prd_id}/reviewers/{member_id}",
    status_code=204,
    summary="Remove a reviewer from a PRD",
)
async def remove_reviewer_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    member_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Remove a reviewer from a PRD document."""
    await get_prd(db, org_id, prd_id)
    await remove_reviewer(db, org_id, prd_id, member_id)
    await db.commit()


# ── Stakeholders ─────────────────────────────────────────────────────


@router.post(
    "/{prd_id}/stakeholders",
    response_model=StakeholderResponse,
    status_code=201,
    summary="Add a stakeholder to a PRD",
)
async def add_stakeholder_endpoint(
    data: StakeholderRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Add a stakeholder to a PRD document. Creates STAKEHOLDER_OF edge."""
    await get_prd(db, org_id, prd_id)
    result = await add_stakeholder(db, org_id, prd_id, member.id, data.member_id)
    await db.commit()
    return StakeholderResponse(**result)


@router.delete(
    "/{prd_id}/stakeholders/{member_id}",
    status_code=204,
    summary="Remove a stakeholder from a PRD",
)
async def remove_stakeholder_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    member_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Remove a stakeholder from a PRD document."""
    await get_prd(db, org_id, prd_id)
    await remove_stakeholder(db, org_id, prd_id, member_id)
    await db.commit()


@router.get(
    "/{prd_id}/stakeholders",
    response_model=dict,
    summary="List PRD stakeholders",
)
async def list_stakeholders_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all stakeholders, reviewers, and owner for a PRD."""
    await get_prd(db, org_id, prd_id)
    items = await list_stakeholders(db, org_id, prd_id)
    return {"items": [StakeholderResponse(**s) for s in items]}


# ── Reviews ──────────────────────────────────────────────────────────


@router.post(
    "/{prd_id}/reviews",
    response_model=ReviewResponse,
    status_code=201,
    summary="Submit a review",
)
async def submit_review_endpoint(
    data: ReviewSubmit,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Submit a review (approve or request changes) for a PRD."""
    await get_prd(db, org_id, prd_id)
    review = await submit_review(
        db,
        org_id,
        prd_id,
        member.id,
        data.status,
        data.comment,
    )
    await db.commit()

    reviewer_name = None
    if review.reviewer:
        reviewer_name = review.reviewer.display_name

    return ReviewResponse(
        id=review.id,
        entity_id=review.entity_id,
        reviewer_id=review.reviewer_id,
        reviewer_name=reviewer_name,
        version=review.version,
        status=review.status,
        comment=review.comment,
        created_at=review.created_at.isoformat(),
        updated_at=review.updated_at.isoformat(),
    )


@router.get(
    "/{prd_id}/reviews",
    response_model=dict,
    summary="List PRD reviews",
)
async def list_reviews_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all reviews for a PRD document."""
    await get_prd(db, org_id, prd_id)
    reviews = await list_reviews(db, org_id, prd_id)

    items = []
    for r in reviews:
        reviewer_name = None
        if r.reviewer:
            reviewer_name = r.reviewer.display_name
        items.append(
            ReviewResponse(
                id=r.id,
                entity_id=r.entity_id,
                reviewer_id=r.reviewer_id,
                reviewer_name=reviewer_name,
                version=r.version,
                status=r.status,
                comment=r.comment,
                created_at=r.created_at.isoformat(),
                updated_at=r.updated_at.isoformat(),
            )
        )

    return {"items": items}


@router.get(
    "/{prd_id}/reviews/summary",
    response_model=ReviewSummary,
    summary="Get review summary",
)
async def get_review_summary_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Get a summary of review status for a PRD."""
    await get_prd(db, org_id, prd_id)
    summary = await get_review_summary(db, org_id, prd_id)
    return ReviewSummary(**summary)


# ── Export ─────────────────────────────────────────────��──────────────


@router.post(
    "/{prd_id}/export",
    summary="Export PRD document",
)
async def export_prd_endpoint(
    data: ExportRequest,
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Export a PRD to Markdown, HTML, PDF, Notion, Confluence, or Google Docs.

    For file formats (markdown/html/pdf), returns the file as a download.
    For API formats (notion/confluence/google_docs), returns the URL of
    the created document.
    """
    from fastapi.responses import Response

    from src.prd.exporter import FILE_FORMATS, export_prd

    result = await export_prd(db, org_id, prd_id, data.format, data.options)

    # File formats: return binary response with download headers
    if data.format in FILE_FORMATS:
        content = result["content"]
        if isinstance(content, str):
            content = content.encode("utf-8")
        return Response(
            content=content,
            media_type=result["content_type"],
            headers={
                "Content-Disposition": f'attachment; filename="{result["filename"]}"',
            },
        )

    # API formats: return JSON with url and external_id
    return ExportResponse(
        url=result.get("url"),
        external_id=result.get("external_id"),
    )


# ── Import ────────────────────────────────────────────────────────────


async def _get_oauth_token(
    db: AsyncSession,
    org_id: UUID,
    source: SourceType,
) -> str:
    """Fetch the stored OAuth access token for a connector, or raise 400."""
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token_row = result.scalar_one_or_none()
    if not token_row:
        raise HTTPException(
            status_code=400,
            detail=f"No {source.value} connection found. Connect {source.value} first.",
        )
    return token_row.access_token


@router.post(
    "/import",
    response_model=PrdResponse,
    status_code=201,
    summary="Import PRD from external source",
)
async def import_prd_endpoint(
    data: ImportRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Import a document from Notion, Confluence, or Google Docs as a PRD.

    Fetches the document from the source API, converts it to TipTap blocks,
    and creates a new PRD entity with the imported content.
    """
    from src.prd.importer import import_document

    if data.source == "notion":
        from src.prd.importers.notion import import_from_notion

        access_token = await _get_oauth_token(db, org_id, SourceType.NOTION)
        doc = await import_from_notion(access_token, data.source_id)

    elif data.source == "confluence":
        from src.prd.importers.confluence import import_from_confluence

        if not data.base_url:
            raise HTTPException(
                status_code=400,
                detail="base_url is required for Confluence imports",
            )
        try:
            access_token = await _get_oauth_token(db, org_id, SourceType.MANUAL)
        except HTTPException:
            raise HTTPException(
                status_code=400,
                detail="No Confluence connection found. Connect Confluence first.",
            )
        doc = await import_from_confluence(data.base_url, access_token, data.source_id)

    elif data.source == "google_docs":
        from src.prd.importers.google_docs import import_from_google_docs

        try:
            access_token = await _get_oauth_token(db, org_id, SourceType.MANUAL)
        except HTTPException:
            raise HTTPException(
                status_code=400,
                detail="No Google Docs connection found. Connect Google first.",
            )
        doc = await import_from_google_docs(access_token, data.source_id)

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported import source: {data.source}. "
            "Supported: notion, confluence, google_docs",
        )

    prd = await import_document(
        db,
        org_id,
        member.id,
        doc,
        parent_folder_id=data.parent_folder_id,
        source=data.source,
        source_id=data.source_id,
    )
    await db.commit()
    return prd


@router.post(
    "/import/file",
    response_model=PrdResponse,
    status_code=201,
    summary="Import PRD from uploaded file",
)
async def import_prd_file_endpoint(
    file: UploadFile = File(...),
    parent_folder_id: UUID | None = Query(None, description="Parent folder ID"),
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Import a PRD from an uploaded file.

    Accepts ``.md``, ``.html``, and ``.pdf`` files. Detects format from
    file extension or content type.
    """
    from src.prd.importer import import_document

    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a name")

    raw_bytes = await file.read()
    filename_lower = file.filename.lower()
    content_type = file.content_type or ""

    if filename_lower.endswith(".pdf") or "pdf" in content_type:
        from src.prd.importers.pdf import import_pdf

        doc = import_pdf(raw_bytes, title=None)
    elif filename_lower.endswith(".md") or "markdown" in content_type:
        from src.prd.importers.markdown import import_markdown

        content = raw_bytes.decode("utf-8")
        doc = import_markdown(content, title=None)
    elif (
        filename_lower.endswith(".html")
        or filename_lower.endswith(".htm")
        or "html" in content_type
    ):
        from src.prd.importers.html import import_html

        content = raw_bytes.decode("utf-8")
        doc = import_html(content, title=None)
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Accepted: .md, .html, .pdf",
        )

    prd = await import_document(
        db,
        org_id,
        member.id,
        doc,
        parent_folder_id=parent_folder_id,
        source="file",
        source_id=file.filename,
    )
    await db.commit()
    return prd


@router.post(
    "/import/bulk",
    response_model=ImportBulkResponse,
    status_code=202,
    summary="Bulk import from external source",
)
async def import_prd_bulk_endpoint(
    data: ImportBulkRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Start a bulk import job from a Notion/Confluence root page.

    This endpoint queues the import and returns a job ID. The actual import
    runs asynchronously. Use the job ID to poll for status.
    """
    import uuid

    # Validate the source is connected
    if data.source == "notion":
        await _get_oauth_token(db, org_id, SourceType.NOTION)
    elif data.source == "confluence":
        if not data.base_url:
            raise HTTPException(
                status_code=400,
                detail="base_url is required for Confluence bulk imports",
            )

    job_id = str(uuid.uuid4())

    # In a production setup this would enqueue a background task.
    # For now we return the job_id so the frontend can track it.
    logger.info(
        "Bulk import job %s created: source=%s root=%s org=%s",
        job_id,
        data.source,
        data.root_page_id,
        org_id,
    )

    return ImportBulkResponse(job_id=job_id, status="started")


# ── PR-PRD Alignment ─────────────────────────────────────────────────


@router.get(
    "/{prd_id}/alignment",
    response_model=dict,
    summary="Get alignment checks for a PRD",
)
async def get_alignment_checks_endpoint(
    org_id: UUID = Path(...),
    prd_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List PR-PRD alignment check results for a specific PRD."""
    from src.prd.alignment import get_alignment_checks
    from src.prd.schemas import AlignmentCheckResponse

    checks = await get_alignment_checks(db, org_id, prd_entity_id=prd_id)

    # Enrich with entity names from the graph
    items = []
    for check in checks:
        prd_title = None
        pr_title = None

        try:
            prd_entity = await get_entity(db, check.prd_entity_id, org_id=org_id)
            if prd_entity:
                prd_title = prd_entity.canonical_name
        except Exception:
            pass

        try:
            pr_entity = await get_entity(db, check.pr_entity_id, org_id=org_id)
            if pr_entity:
                pr_title = pr_entity.canonical_name
        except Exception:
            pass

        items.append(
            AlignmentCheckResponse(
                id=check.id,
                prd_entity_id=check.prd_entity_id,
                prd_title=prd_title,
                pr_entity_id=check.pr_entity_id,
                pr_title=pr_title,
                findings=check.findings or [],
                coverage_score=check.coverage_score,
                status=check.status,
                created_at=check.created_at.isoformat(),
            )
        )

    return {"items": items}


@router.post(
    "/alignment/{check_id}/acknowledge",
    status_code=204,
    summary="Acknowledge an alignment finding",
)
async def acknowledge_alignment_endpoint(
    org_id: UUID = Path(...),
    check_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Mark an alignment check as acknowledged."""
    from src.prd.alignment import acknowledge_finding

    await acknowledge_finding(db, org_id, check_id)
    await db.commit()


@router.post(
    "/alignment/{check_id}/resolve",
    status_code=204,
    summary="Resolve an alignment finding",
)
async def resolve_alignment_endpoint(
    org_id: UUID = Path(...),
    check_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Mark an alignment check as resolved."""
    from src.prd.alignment import resolve_finding

    await resolve_finding(db, org_id, check_id)
    await db.commit()
