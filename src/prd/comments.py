"""Comment and reaction service functions for PRD documents.

Handles threaded comments, resolve/unresolve, and emoji reaction toggling.
All queries scoped by org_id.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.shared.models import PrdComment, PrdReaction

logger = logging.getLogger(__name__)


# ── Comments ─────────────────────────────────────────────────────────


async def create_comment(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    block_id: UUID | None,
    parent_id: UUID | None,
    content: str,
) -> PrdComment:
    """Create a new comment on a PRD document or block."""
    # Validate parent_id if provided
    if parent_id is not None:
        result = await db.execute(
            select(PrdComment).where(
                PrdComment.id == parent_id,
                PrdComment.org_id == org_id,
                PrdComment.entity_id == entity_id,
            )
        )
        parent = result.scalar_one_or_none()
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent comment not found")

    comment = PrdComment(
        id=uuid.uuid4(),
        org_id=org_id,
        entity_id=entity_id,
        block_id=block_id,
        parent_id=parent_id,
        author_id=member_id,
        content=content,
    )
    db.add(comment)
    await db.flush()

    # Reload with author relationship
    result = await db.execute(
        select(PrdComment)
        .where(PrdComment.id == comment.id)
        .options(
            selectinload(PrdComment.author),
            selectinload(PrdComment.replies).selectinload(PrdComment.author),
        )
    )
    return result.scalar_one()


async def list_comments(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    block_id: UUID | None = None,
    resolved: bool | None = None,
) -> list[PrdComment]:
    """List comments for a PRD, optionally filtered by block and resolution status.

    Returns only top-level comments (parent_id is None) with replies eagerly loaded.
    """
    query = (
        select(PrdComment)
        .where(
            PrdComment.org_id == org_id,
            PrdComment.entity_id == entity_id,
            PrdComment.parent_id.is_(None),
        )
        .options(
            selectinload(PrdComment.author),
            selectinload(PrdComment.replies).selectinload(PrdComment.author),
        )
        .order_by(PrdComment.created_at)
    )

    if block_id is not None:
        query = query.where(PrdComment.block_id == block_id)

    if resolved is not None:
        query = query.where(PrdComment.is_resolved == resolved)

    result = await db.execute(query)
    return list(result.scalars().all())


async def update_comment(
    db: AsyncSession,
    org_id: UUID,
    comment_id: UUID,
    member_id: UUID,
    content: str,
) -> PrdComment:
    """Update a comment's content. Only the author can edit."""
    result = await db.execute(
        select(PrdComment)
        .where(
            PrdComment.id == comment_id,
            PrdComment.org_id == org_id,
        )
        .options(
            selectinload(PrdComment.author),
            selectinload(PrdComment.replies).selectinload(PrdComment.author),
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != member_id:
        raise HTTPException(status_code=403, detail="Only the author can edit this comment")

    comment.content = content
    await db.flush()
    return comment


async def delete_comment(
    db: AsyncSession,
    org_id: UUID,
    comment_id: UUID,
    member_id: UUID,
) -> None:
    """Delete a comment. Only the author can delete."""
    result = await db.execute(
        select(PrdComment).where(
            PrdComment.id == comment_id,
            PrdComment.org_id == org_id,
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != member_id:
        raise HTTPException(status_code=403, detail="Only the author can delete this comment")

    # Delete child replies first
    await db.execute(
        delete(PrdComment).where(
            PrdComment.parent_id == comment_id,
            PrdComment.org_id == org_id,
        )
    )
    await db.execute(
        delete(PrdComment).where(
            PrdComment.id == comment_id,
            PrdComment.org_id == org_id,
        )
    )
    await db.flush()


async def resolve_comment(
    db: AsyncSession,
    org_id: UUID,
    comment_id: UUID,
    member_id: UUID,
) -> PrdComment:
    """Mark a comment thread as resolved."""
    result = await db.execute(
        select(PrdComment)
        .where(
            PrdComment.id == comment_id,
            PrdComment.org_id == org_id,
        )
        .options(
            selectinload(PrdComment.author),
            selectinload(PrdComment.replies).selectinload(PrdComment.author),
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.is_resolved = True
    comment.resolved_by = member_id
    comment.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return comment


async def unresolve_comment(
    db: AsyncSession,
    org_id: UUID,
    comment_id: UUID,
    member_id: UUID,
) -> PrdComment:
    """Re-open a resolved comment thread."""
    result = await db.execute(
        select(PrdComment)
        .where(
            PrdComment.id == comment_id,
            PrdComment.org_id == org_id,
        )
        .options(
            selectinload(PrdComment.author),
            selectinload(PrdComment.replies).selectinload(PrdComment.author),
        )
    )
    comment = result.scalar_one_or_none()
    if comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")

    comment.is_resolved = False
    comment.resolved_by = None
    comment.resolved_at = None
    await db.flush()
    return comment


# ── Reactions ────────────────────────────────────────────────────────


async def toggle_reaction(
    db: AsyncSession,
    org_id: UUID,
    block_id: UUID,
    member_id: UUID,
    emoji: str,
) -> dict:
    """Toggle a reaction on a block - add if not exists, remove if exists.

    Returns ``{added: bool, reactions: list[dict]}`` with the updated reaction
    summary for the block.
    """
    # Check if reaction already exists
    result = await db.execute(
        select(PrdReaction).where(
            PrdReaction.org_id == org_id,
            PrdReaction.block_id == block_id,
            PrdReaction.member_id == member_id,
            PrdReaction.emoji == emoji,
        )
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Remove existing reaction
        await db.execute(delete(PrdReaction).where(PrdReaction.id == existing.id))
        added = False
    else:
        # Add new reaction
        reaction = PrdReaction(
            id=uuid.uuid4(),
            org_id=org_id,
            block_id=block_id,
            member_id=member_id,
            emoji=emoji,
        )
        db.add(reaction)
        added = True

    await db.flush()

    # Return updated reaction summary
    reactions = await get_block_reactions(db, org_id, block_id)
    return {"added": added, "reactions": reactions}


async def get_block_reactions(
    db: AsyncSession,
    org_id: UUID,
    block_id: UUID,
) -> list[dict]:
    """Get grouped reactions for a block.

    Returns a list of ``{emoji, count, member_ids}`` dicts grouped by emoji.
    """
    result = await db.execute(
        select(PrdReaction).where(
            PrdReaction.org_id == org_id,
            PrdReaction.block_id == block_id,
        )
    )
    rows = result.scalars().all()

    # Group by emoji
    grouped: dict[str, list[UUID]] = {}
    for row in rows:
        grouped.setdefault(row.emoji, []).append(row.member_id)

    return [
        {
            "emoji": emoji,
            "count": len(member_ids),
            "member_ids": member_ids,
        }
        for emoji, member_ids in grouped.items()
    ]
