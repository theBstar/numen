"""Block-level operations for PRD documents.

Handles CRUD on prd_blocks rows, version snapshotting, and slug generation.
All queries scoped by org_id. Blocks are ordered by fractional position.
"""

from __future__ import annotations

import logging
import re
import uuid
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.prd.schemas import (
    PrdBlockBatchOp,
    PrdBlockResponse,
    PrdVersionDetail,
    PrdVersionResponse,
)
from src.shared.models import PrdBlock, PrdVersion

logger = logging.getLogger(__name__)


# ── Slug generation ───────────────────────────────────────────────────


def generate_slug(
    block_type: str,
    content: dict,
    position: float,
    existing_slugs: set[str],
) -> str:
    """Generate a URL-friendly slug for a block.

    For headings, extracts text and slugifies it. For other block types,
    uses ``{block_type}-{position_int}``. Appends ``-2``, ``-3``, etc.
    to guarantee uniqueness within the document.
    """
    base = ""

    if block_type == "heading":
        # Extract text from TipTap-style content
        text = _extract_text_from_content(content)
        if text:
            base = _slugify(text)

    if not base:
        base = f"{block_type}-{int(position)}"

    # Ensure uniqueness
    slug = base
    counter = 2
    while slug in existing_slugs:
        slug = f"{base}-{counter}"
        counter += 1

    return slug


def _extract_text_from_content(content: dict) -> str:
    """Recursively extract plain text from TipTap JSON content."""
    parts: list[str] = []

    if "text" in content:
        parts.append(content["text"])

    for child in content.get("content", []):
        if isinstance(child, dict):
            parts.append(_extract_text_from_content(child))

    return " ".join(parts).strip()


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug[:128] if slug else "untitled"


# ── Block CRUD ────────────────────────────────────────────────────────


async def get_blocks(db: AsyncSession, org_id: UUID, entity_id: UUID) -> list[PrdBlockResponse]:
    """Return all blocks for a PRD entity, ordered by position."""
    result = await db.execute(
        select(PrdBlock)
        .where(
            PrdBlock.org_id == org_id,
            PrdBlock.entity_id == entity_id,
        )
        .order_by(PrdBlock.position)
    )
    rows = result.scalars().all()

    return [
        PrdBlockResponse(
            id=row.id,
            entity_id=row.entity_id,
            parent_id=row.parent_id,
            slug=row.slug,
            block_type=row.block_type,
            content=row.content or {},
            position=row.position,
            heading_level=row.heading_level,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


async def batch_update_blocks(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    ops: list[PrdBlockBatchOp],
) -> list[PrdBlockResponse]:
    """Process a batch of create/update/delete operations on blocks.

    Returns the full list of current blocks after all operations.
    """
    # Collect existing slugs for uniqueness checks
    existing_result = await db.execute(
        select(PrdBlock.slug).where(
            PrdBlock.org_id == org_id,
            PrdBlock.entity_id == entity_id,
        )
    )
    existing_slugs: set[str] = {row[0] for row in existing_result.all()}

    for op in ops:
        if op.op == "create":
            await _create_block(db, org_id, entity_id, member_id, op, existing_slugs)
        elif op.op == "update":
            await _update_block(db, org_id, entity_id, op, existing_slugs)
        elif op.op == "delete":
            await _delete_block(db, org_id, entity_id, op)
        else:
            logger.warning("Unknown block operation: %s", op.op)

    await db.flush()

    return await get_blocks(db, org_id, entity_id)


async def _create_block(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    op: PrdBlockBatchOp,
    existing_slugs: set[str],
) -> None:
    """Create a new block row."""
    block_type = op.block_type or "paragraph"
    content = op.content or {}
    position = op.position if op.position is not None else 0.0

    slug = generate_slug(block_type, content, position, existing_slugs)
    existing_slugs.add(slug)

    block = PrdBlock(
        id=uuid.uuid4(),
        org_id=org_id,
        entity_id=entity_id,
        parent_id=op.parent_id,
        slug=slug,
        block_type=block_type,
        content=content,
        position=position,
        heading_level=op.heading_level,
        created_by=member_id,
    )
    db.add(block)


async def _update_block(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    op: PrdBlockBatchOp,
    existing_slugs: set[str],
) -> None:
    """Update an existing block's content, position, or heading_level."""
    if op.id is None:
        logger.warning("Block update requires an id")
        return

    values: dict = {}
    if op.content is not None:
        values["content"] = op.content
        # Re-generate slug if content changed on a heading
        block_result = await db.execute(
            select(PrdBlock.block_type, PrdBlock.slug).where(
                PrdBlock.id == op.id,
                PrdBlock.org_id == org_id,
                PrdBlock.entity_id == entity_id,
            )
        )
        block_row = block_result.first()
        if block_row and block_row.block_type == "heading":
            existing_slugs.discard(block_row.slug)
            position = op.position if op.position is not None else 0.0
            new_slug = generate_slug("heading", op.content, position, existing_slugs)
            existing_slugs.add(new_slug)
            values["slug"] = new_slug

    if op.position is not None:
        values["position"] = op.position
    if op.heading_level is not None:
        values["heading_level"] = op.heading_level

    if values:
        await db.execute(
            update(PrdBlock)
            .where(
                PrdBlock.id == op.id,
                PrdBlock.org_id == org_id,
                PrdBlock.entity_id == entity_id,
            )
            .values(**values)
        )


async def _delete_block(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    op: PrdBlockBatchOp,
) -> None:
    """Delete a block row."""
    if op.id is None:
        logger.warning("Block delete requires an id")
        return

    await db.execute(
        delete(PrdBlock).where(
            PrdBlock.id == op.id,
            PrdBlock.org_id == org_id,
            PrdBlock.entity_id == entity_id,
        )
    )


# ── Version management ────────────────────────────────────────────────


async def create_version(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    status: str,
    message: str | None = None,
) -> PrdVersionResponse:
    """Snapshot the current blocks into a new version row."""
    # Get current blocks as snapshot
    blocks = await get_blocks(db, org_id, entity_id)
    snapshot = {
        "blocks": [
            {
                "id": str(b.id),
                "slug": b.slug,
                "block_type": b.block_type,
                "content": b.content,
                "position": b.position,
                "heading_level": b.heading_level,
                "parent_id": str(b.parent_id) if b.parent_id else None,
            }
            for b in blocks
        ]
    }

    # Get next version number
    current_max = await db.execute(
        select(func.max(PrdVersion.version)).where(
            PrdVersion.entity_id == entity_id,
            PrdVersion.org_id == org_id,
        )
    )
    max_version = current_max.scalar_one() or 0
    next_version = max_version + 1

    version_row = PrdVersion(
        id=uuid.uuid4(),
        org_id=org_id,
        entity_id=entity_id,
        version=next_version,
        snapshot=snapshot,
        status_at=status,
        created_by=member_id,
        message=message,
    )
    db.add(version_row)
    await db.flush()

    return PrdVersionResponse(
        id=version_row.id,
        entity_id=version_row.entity_id,
        version=version_row.version,
        status_at=version_row.status_at,
        created_by=version_row.created_by,
        message=version_row.message,
        created_at=version_row.created_at,
    )


async def get_versions(db: AsyncSession, org_id: UUID, entity_id: UUID) -> list[PrdVersionResponse]:
    """List all versions for a PRD entity, ordered by version number."""
    result = await db.execute(
        select(PrdVersion)
        .where(
            PrdVersion.org_id == org_id,
            PrdVersion.entity_id == entity_id,
        )
        .order_by(PrdVersion.version.desc())
    )
    rows = result.scalars().all()

    return [
        PrdVersionResponse(
            id=row.id,
            entity_id=row.entity_id,
            version=row.version,
            status_at=row.status_at,
            created_by=row.created_by,
            message=row.message,
            created_at=row.created_at,
        )
        for row in rows
    ]


async def get_version_detail(
    db: AsyncSession, org_id: UUID, entity_id: UUID, version: int
) -> PrdVersionDetail:
    """Get a specific version with its full block snapshot."""
    result = await db.execute(
        select(PrdVersion).where(
            PrdVersion.org_id == org_id,
            PrdVersion.entity_id == entity_id,
            PrdVersion.version == version,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Version not found")

    return PrdVersionDetail(
        id=row.id,
        entity_id=row.entity_id,
        version=row.version,
        status_at=row.status_at,
        created_by=row.created_by,
        message=row.message,
        created_at=row.created_at,
        snapshot=row.snapshot or {},
    )
