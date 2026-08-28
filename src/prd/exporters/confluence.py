"""Confluence exporter - create a Confluence page from TipTap JSON blocks.

Converts TipTap block structure to Atlassian Document Format (ADF) and
creates a page via the Confluence REST API v2. ADF is ProseMirror-based,
so the mapping from TipTap is fairly direct. Uses httpx for async HTTP.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def export_to_confluence(
    base_url: str,
    access_token: str,
    blocks: list[dict],
    title: str,
    space_key: str | None = None,
    parent_page_id: str | None = None,
) -> dict:
    """Create a Confluence page from TipTap JSON blocks.

    Args:
        base_url: Confluence instance base URL (e.g. https://your-domain.atlassian.net).
        access_token: Confluence API token (Basic auth or OAuth Bearer).
        blocks: List of TipTap block dicts.
        title: Page title.
        space_key: Confluence space key (required if no parent_page_id).
        parent_page_id: Optional parent page ID for nesting.

    Returns:
        {"url": str, "external_id": str} with the created page URL and ID.
    """
    adf_doc = _convert_blocks_to_adf(blocks)

    # Build the page creation payload (API v2)
    page_data: dict[str, Any] = {
        "type": "page",
        "title": title,
        "body": {
            "representation": "atlas_doc_format",
            "value": adf_doc,
        },
    }

    if space_key:
        page_data["spaceId"] = space_key
    if parent_page_id:
        page_data["parentId"] = parent_page_id

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Try API v2 first
        url = f"{base_url.rstrip('/')}/wiki/api/v2/pages"
        response = await client.post(url, json=page_data, headers=headers)

        if response.status_code not in (200, 201):
            logger.error("Confluence API error %d: %s", response.status_code, response.text)
            raise RuntimeError(f"Confluence API error {response.status_code}: {response.text}")

        result = response.json()

        page_id = result.get("id", "")
        page_url = result.get("_links", {}).get("webui", "")
        if page_url and not page_url.startswith("http"):
            page_url = f"{base_url.rstrip('/')}/wiki{page_url}"

        return {
            "url": page_url,
            "external_id": str(page_id),
        }


# ── ADF document conversion ─────────────────────────────────────────


def _convert_blocks_to_adf(blocks: list[dict]) -> str:
    """Convert TipTap blocks to an ADF document JSON string."""
    import json

    adf_nodes: list[dict] = []

    for block in blocks:
        block_type = block.get("block_type", "paragraph")
        content = block.get("content", {})
        heading_level = block.get("heading_level")

        converted = _convert_block(block_type, content, heading_level)
        if converted:
            if isinstance(converted, list):
                adf_nodes.extend(converted)
            else:
                adf_nodes.append(converted)

    adf_doc = {
        "version": 1,
        "type": "doc",
        "content": adf_nodes,
    }

    return json.dumps(adf_doc)


def _convert_block(
    block_type: str,
    content: dict,
    heading_level: int | None = None,
) -> dict | list[dict] | None:
    """Convert a single TipTap block to ADF node(s)."""
    if block_type == "heading":
        return _convert_heading(content, heading_level)
    elif block_type == "paragraph":
        return _convert_paragraph(content)
    elif block_type == "codeBlock":
        return _convert_code_block(content)
    elif block_type == "bulletList":
        return _convert_bullet_list(content)
    elif block_type == "orderedList":
        return _convert_ordered_list(content)
    elif block_type == "taskList":
        return _convert_task_list(content)
    elif block_type == "blockquote":
        return _convert_blockquote(content)
    elif block_type == "image":
        return _convert_image(content)
    elif block_type == "horizontalRule":
        return {"type": "rule"}
    elif block_type == "table":
        return _convert_table(content)
    else:
        # Fallback: paragraph
        inline_nodes = _tiptap_inline_to_adf(content.get("content", []))
        if inline_nodes:
            return {"type": "paragraph", "content": inline_nodes}
        return None


def _convert_heading(content: dict, heading_level: int | None) -> dict:
    level = heading_level or content.get("attrs", {}).get("level", 2)
    # ADF supports levels 1-6
    level = max(1, min(6, level))
    inline_nodes = _tiptap_inline_to_adf(content.get("content", []))
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": inline_nodes,
    }


def _convert_paragraph(content: dict) -> dict:
    inline_nodes = _tiptap_inline_to_adf(content.get("content", []))
    return {"type": "paragraph", "content": inline_nodes}


def _convert_code_block(content: dict) -> dict:
    language = content.get("attrs", {}).get("language", "")
    code_text = _extract_plain_text(content.get("content", []))
    node: dict[str, Any] = {
        "type": "codeBlock",
        "content": [{"type": "text", "text": code_text}],
    }
    if language:
        node["attrs"] = {"language": language}
    return node


def _convert_bullet_list(content: dict) -> dict:
    items = content.get("content", [])
    list_items: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        list_items.append(_convert_list_item(item))

    return {"type": "bulletList", "content": list_items}


def _convert_ordered_list(content: dict) -> dict:
    items = content.get("content", [])
    list_items: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        list_items.append(_convert_list_item(item))

    node: dict[str, Any] = {"type": "orderedList", "content": list_items}
    start = content.get("attrs", {}).get("start")
    if start and start != 1:
        node["attrs"] = {"order": start}
    return node


def _convert_list_item(item: dict) -> dict:
    """Convert a TipTap list item to ADF listItem."""
    child_nodes: list[dict] = []

    for child in item.get("content", []):
        if not isinstance(child, dict):
            continue
        child_type = child.get("type", "")
        if child_type == "paragraph":
            inline_nodes = _tiptap_inline_to_adf(child.get("content", []))
            child_nodes.append({"type": "paragraph", "content": inline_nodes})
        elif child_type == "bulletList":
            child_nodes.append(_convert_bullet_list(child))
        elif child_type == "orderedList":
            child_nodes.append(_convert_ordered_list(child))

    return {"type": "listItem", "content": child_nodes}


def _convert_task_list(content: dict) -> list[dict]:
    """Convert TipTap taskList to ADF.

    ADF does not have a native task list type, so we convert to
    paragraphs with checkbox-style text prefixes.
    """
    items = content.get("content", [])
    adf_nodes: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        checked = item.get("attrs", {}).get("checked", False)
        prefix = "[x] " if checked else "[ ] "

        for child in item.get("content", []):
            if isinstance(child, dict) and child.get("type") == "paragraph":
                inline_nodes = _tiptap_inline_to_adf(child.get("content", []))
                # Prepend checkbox text
                checkbox_node = {"type": "text", "text": prefix}
                adf_nodes.append(
                    {
                        "type": "paragraph",
                        "content": [checkbox_node] + inline_nodes,
                    }
                )

    return adf_nodes


def _convert_blockquote(content: dict) -> dict:
    inner = content.get("content", [])
    child_nodes: list[dict] = []

    for child in inner:
        if isinstance(child, dict) and child.get("type") == "paragraph":
            inline_nodes = _tiptap_inline_to_adf(child.get("content", []))
            child_nodes.append({"type": "paragraph", "content": inline_nodes})

    return {"type": "blockquote", "content": child_nodes}


def _convert_image(content: dict) -> dict:
    attrs = content.get("attrs", {})
    src = attrs.get("src", "")

    return {
        "type": "mediaSingle",
        "attrs": {"layout": "center"},
        "content": [
            {
                "type": "media",
                "attrs": {
                    "type": "external",
                    "url": src,
                },
            }
        ],
    }


def _convert_table(content: dict) -> dict:
    rows = content.get("content", [])
    adf_rows: list[dict] = []

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        cells = row.get("content", [])
        adf_cells: list[dict] = []
        is_header = idx == 0

        for cell in cells:
            if not isinstance(cell, dict):
                continue
            cell_content = cell.get("content", [])
            cell_nodes: list[dict] = []

            for child in cell_content:
                if isinstance(child, dict) and child.get("type") == "paragraph":
                    inline_nodes = _tiptap_inline_to_adf(child.get("content", []))
                    cell_nodes.append({"type": "paragraph", "content": inline_nodes})

            if not cell_nodes:
                cell_nodes = [{"type": "paragraph", "content": []}]

            cell_type = "tableHeader" if is_header else "tableCell"
            adf_cell: dict[str, Any] = {"type": cell_type, "content": cell_nodes}

            # Handle colspan/rowspan
            cell_attrs = cell.get("attrs", {})
            extra_attrs: dict[str, Any] = {}
            if cell_attrs.get("colspan", 1) > 1:
                extra_attrs["colspan"] = cell_attrs["colspan"]
            if cell_attrs.get("rowspan", 1) > 1:
                extra_attrs["rowspan"] = cell_attrs["rowspan"]
            if extra_attrs:
                adf_cell["attrs"] = extra_attrs

            adf_cells.append(adf_cell)

        adf_rows.append({"type": "tableRow", "content": adf_cells})

    return {"type": "table", "content": adf_rows}


# ── Inline conversion ────────────────────────────────────────────────


def _tiptap_inline_to_adf(nodes: list) -> list[dict]:
    """Convert TipTap inline nodes to ADF inline nodes."""
    adf_nodes: list[dict] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type", "")

        if node_type == "text":
            text_content = node.get("text", "")
            marks = node.get("marks", [])
            adf_marks = _tiptap_marks_to_adf(marks)

            adf_node: dict[str, Any] = {"type": "text", "text": text_content}
            if adf_marks:
                adf_node["marks"] = adf_marks
            adf_nodes.append(adf_node)

        elif node_type == "hardBreak":
            adf_nodes.append({"type": "hardBreak"})

        elif node_type == "image":
            # Inline images are not directly supported in ADF inline context
            attrs = node.get("attrs", {})
            src = attrs.get("src", "")
            alt = attrs.get("alt", "image")
            adf_nodes.append(
                {
                    "type": "text",
                    "text": f"[{alt}]({src})",
                    "marks": [{"type": "link", "attrs": {"href": src}}],
                }
            )

        elif node_type == "mention":
            attrs = node.get("attrs", {})
            label = attrs.get("label", attrs.get("id", ""))
            adf_nodes.append(
                {
                    "type": "text",
                    "text": f"@{label}",
                    "marks": [{"type": "strong"}],
                }
            )

    return adf_nodes


def _tiptap_marks_to_adf(marks: list) -> list[dict]:
    """Convert TipTap marks to ADF marks."""
    adf_marks: list[dict] = []

    for mark in marks:
        mark_type = mark.get("type", "")
        attrs = mark.get("attrs", {})

        if mark_type == "bold":
            adf_marks.append({"type": "strong"})
        elif mark_type == "italic":
            adf_marks.append({"type": "em"})
        elif mark_type == "code":
            adf_marks.append({"type": "code"})
        elif mark_type == "strike":
            adf_marks.append({"type": "strike"})
        elif mark_type == "underline":
            adf_marks.append({"type": "underline"})
        elif mark_type == "link":
            href = attrs.get("href", "")
            adf_marks.append({"type": "link", "attrs": {"href": href}})

    return adf_marks


def _extract_plain_text(nodes: list) -> str:
    """Extract plain text from TipTap inline nodes."""
    parts: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        else:
            inner = _extract_plain_text(node.get("content", []))
            if inner:
                parts.append(inner)
    return "".join(parts)
