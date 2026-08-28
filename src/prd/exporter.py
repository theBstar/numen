"""Core export abstraction. All exporters consume TipTap JSON blocks.

Loads PRD entity and blocks, delegates to the appropriate format-specific
exporter, and returns the result. File formats return content bytes;
API formats return external URLs.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_repository import get_entity
from src.prd.blocks import get_blocks

logger = logging.getLogger(__name__)

# Valid export formats
FILE_FORMATS = {"markdown", "html", "pdf"}
API_FORMATS = {"notion", "confluence", "google_docs"}
ALL_FORMATS = FILE_FORMATS | API_FORMATS


async def export_prd(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    format: str,
    options: dict | None = None,
) -> dict:
    """Export a PRD to the specified format.

    Args:
        db: Async database session.
        org_id: Organization ID (tenant boundary).
        entity_id: PRD entity ID.
        format: "markdown" | "html" | "pdf" | "notion" | "confluence" | "google_docs"
        options: Format-specific options.

    Returns:
        For file formats (markdown/html/pdf):
            {"content": bytes, "filename": str, "content_type": str}
        For API formats (notion/confluence/google_docs):
            {"url": str, "external_id": str}

    Raises:
        HTTPException: If PRD not found or format is invalid.
    """
    if format not in ALL_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid export format: {format}. "
            f"Supported formats: {', '.join(sorted(ALL_FORMATS))}",
        )

    options = options or {}

    # Load PRD entity from FalkorDB
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="PRD not found")

    props = entity.properties
    if isinstance(props, str):
        props = json.loads(props)

    title = entity.canonical_name or "Untitled PRD"

    # Build metadata dict from entity properties
    metadata = _build_metadata(entity, props)

    # Load blocks from PostgreSQL ordered by position
    block_rows = await get_blocks(db, org_id, entity_id)
    blocks = [
        {
            "block_type": b.block_type,
            "content": b.content or {},
            "heading_level": b.heading_level,
            "slug": b.slug,
            "position": b.position,
        }
        for b in block_rows
    ]

    # Delegate to format-specific exporter
    if format == "markdown":
        return await _export_markdown(title, blocks, metadata)
    elif format == "html":
        return await _export_html(title, blocks, metadata, options)
    elif format == "pdf":
        return await _export_pdf(title, blocks, metadata)
    elif format == "notion":
        return await _export_notion(title, blocks, options)
    elif format == "confluence":
        return await _export_confluence(title, blocks, options)
    elif format == "google_docs":
        return await _export_google_docs(title, blocks, options)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")


# ── Metadata builder ─────────────────────────────────────────────────


def _build_metadata(entity, props: dict) -> dict:
    """Build a metadata dict from PRD entity properties."""
    return {
        "status": props.get("prd_status", "draft"),
        "owner": props.get("owner_name") or None,
        "priority": props.get("priority", "medium"),
        "target_date": props.get("target_date"),
        "tags": props.get("tags", []) or [],
        "description": props.get("description"),
    }


# ── Format-specific delegates ────────────────────────────────────────


async def _export_markdown(
    title: str,
    blocks: list[dict],
    metadata: dict,
) -> dict:
    from src.prd.exporters.markdown import export_to_markdown

    include_frontmatter = True  # default
    md_content = export_to_markdown(
        title,
        blocks,
        metadata=metadata if include_frontmatter else None,
    )

    filename = _slugify(title) + ".md"
    return {
        "content": md_content.encode("utf-8"),
        "filename": filename,
        "content_type": "text/markdown; charset=utf-8",
    }


async def _export_html(
    title: str,
    blocks: list[dict],
    metadata: dict,
    options: dict,
) -> dict:
    from src.prd.exporters.html import export_to_html

    styled = options.get("styled", True)
    html_content = export_to_html(title, blocks, metadata=metadata, styled=styled)

    filename = _slugify(title) + ".html"
    return {
        "content": html_content.encode("utf-8"),
        "filename": filename,
        "content_type": "text/html; charset=utf-8",
    }


async def _export_pdf(
    title: str,
    blocks: list[dict],
    metadata: dict,
) -> dict:
    from src.prd.exporters.pdf import export_to_pdf

    pdf_bytes = await export_to_pdf(title, blocks, metadata=metadata)

    filename = _slugify(title) + ".pdf"
    return {
        "content": pdf_bytes,
        "filename": filename,
        "content_type": "application/pdf",
    }


async def _export_notion(
    title: str,
    blocks: list[dict],
    options: dict,
) -> dict:
    from src.prd.exporters.notion import export_to_notion

    access_token = options.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Notion export requires 'access_token' in options",
        )

    parent_page_id = options.get("parent_page_id")

    return await export_to_notion(
        access_token=access_token,
        blocks=blocks,
        title=title,
        parent_page_id=parent_page_id,
    )


async def _export_confluence(
    title: str,
    blocks: list[dict],
    options: dict,
) -> dict:
    from src.prd.exporters.confluence import export_to_confluence

    base_url = options.get("base_url")
    access_token = options.get("access_token")
    if not base_url or not access_token:
        raise HTTPException(
            status_code=400,
            detail="Confluence export requires 'base_url' and 'access_token' in options",
        )

    space_key = options.get("space_key")
    parent_page_id = options.get("parent_page_id")

    return await export_to_confluence(
        base_url=base_url,
        access_token=access_token,
        blocks=blocks,
        title=title,
        space_key=space_key,
        parent_page_id=parent_page_id,
    )


async def _export_google_docs(
    title: str,
    blocks: list[dict],
    options: dict,
) -> dict:
    from src.prd.exporters.google_docs import export_to_google_docs

    access_token = options.get("access_token")
    if not access_token:
        raise HTTPException(
            status_code=400,
            detail="Google Docs export requires 'access_token' in options",
        )

    folder_id = options.get("folder_id")

    return await export_to_google_docs(
        access_token=access_token,
        blocks=blocks,
        title=title,
        folder_id=folder_id,
    )


# ── Helpers ──────────────────────────────────────────────────────────


def _slugify(text: str) -> str:
    """Convert title to a filename-safe slug."""
    import re

    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug[:100] if slug else "untitled"
