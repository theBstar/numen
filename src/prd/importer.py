"""Core import abstraction. All importers produce ImportedDocument
which is then converted to PRD entity + blocks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class ImportedMedia:
    """A media asset discovered during document import."""

    url: str  # source URL to download
    file_name: str
    file_type: str


@dataclass
class ImportedBlock:
    """A single content block extracted from an external document."""

    block_type: str  # heading, paragraph, image, code, table, list, callout, divider, embed
    content: dict  # TipTap-compatible JSON node
    heading_level: int | None = None
    children: list[ImportedBlock] = field(default_factory=list)


@dataclass
class ImportedDocument:
    """Intermediate representation of an imported document.

    All format-specific importers produce this dataclass, which is then
    converted to a PRD entity + blocks by ``import_document``.
    """

    title: str
    blocks: list[ImportedBlock]
    metadata: dict = field(default_factory=dict)  # source-specific metadata
    media: list[ImportedMedia] = field(default_factory=list)
    source_url: str | None = None


def _flatten_blocks(blocks: list[ImportedBlock]) -> list[ImportedBlock]:
    """Flatten a tree of ImportedBlocks into a single list (depth-first)."""
    flat: list[ImportedBlock] = []
    for block in blocks:
        flat.append(block)
        if block.children:
            flat.extend(_flatten_blocks(block.children))
    return flat


async def import_document(
    db: AsyncSession,
    org_id: UUID,
    member_id: UUID,
    doc: ImportedDocument,
    parent_folder_id: UUID | None = None,
    source: str = "manual",
    source_id: str | None = None,
) -> dict:
    """Convert an ImportedDocument to a PRD entity + blocks.

    Steps:
        1. Create PRD entity via service.create_prd()
        2. Flatten nested blocks and create batch operations
        3. Persist blocks via blocks.batch_update_blocks()
        4. Return the created PRD response
    """
    from src.prd.blocks import batch_update_blocks
    from src.prd.schemas import PrdBlockBatchOp, PrdCreate
    from src.prd.service import create_prd

    prd_data = PrdCreate(
        title=doc.title,
        node_type="document",
        parent_id=parent_folder_id,
        description=doc.metadata.get("description"),
        tags=doc.metadata.get("tags", []),
    )

    prd = await create_prd(db, org_id, member_id, prd_data)
    prd_id = UUID(str(prd.id))

    # Flatten block tree and build batch operations
    flat_blocks = _flatten_blocks(doc.blocks)
    ops: list[PrdBlockBatchOp] = []
    position = 1.0

    for block in flat_blocks:
        ops.append(
            PrdBlockBatchOp(
                op="create",
                block_type=block.block_type,
                content=block.content,
                position=position,
                heading_level=block.heading_level,
            )
        )
        position += 1.0

    if ops:
        await batch_update_blocks(db, org_id, prd_id, member_id, ops)

    logger.info(
        "Imported document '%s' as PRD %s with %d blocks (source=%s)",
        doc.title,
        prd_id,
        len(ops),
        source,
    )

    return prd
