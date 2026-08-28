"""Import from Confluence REST API v2. Converts ADF to TipTap JSON.

ADF (Atlassian Document Format) is ProseMirror-based and structurally
similar to TipTap JSON, so most node types have a direct mapping.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TipTap node builders
# ---------------------------------------------------------------------------


def _text_node(text: str, marks: list[dict] | None = None) -> dict:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _paragraph_node(content: list[dict]) -> dict:
    return {"type": "paragraph", "content": content}


def _heading_node(level: int, content: list[dict]) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": content,
    }


def _code_block_node(code: str, language: str = "") -> dict:
    return {
        "type": "codeBlock",
        "attrs": {"language": language},
        "content": [{"type": "text", "text": code}],
    }


def _image_node(src: str, alt: str = "") -> dict:
    return {"type": "image", "attrs": {"src": src, "alt": alt}}


def _blockquote_node(content: list[dict]) -> dict:
    return {"type": "blockquote", "content": content}


def _horizontal_rule_node() -> dict:
    return {"type": "horizontalRule"}


def _bullet_list_node(items: list[dict]) -> dict:
    return {"type": "bulletList", "content": items}


def _ordered_list_node(items: list[dict]) -> dict:
    return {"type": "orderedList", "content": items}


def _list_item_node(content: list[dict]) -> dict:
    return {"type": "listItem", "content": content}


def _table_node(rows: list[dict]) -> dict:
    return {"type": "table", "content": rows}


def _table_row_node(cells: list[dict]) -> dict:
    return {"type": "tableRow", "content": cells}


def _table_cell_node(content: list[dict], header: bool = False) -> dict:
    cell_type = "tableHeader" if header else "tableCell"
    return {"type": cell_type, "content": content}


# ---------------------------------------------------------------------------
# ADF mark -> TipTap mark
# ---------------------------------------------------------------------------


def _convert_adf_mark(mark: dict) -> dict | None:
    """Convert a single ADF mark to a TipTap mark."""
    mark_type = mark.get("type", "")
    attrs = mark.get("attrs", {})

    mapping: dict[str, str] = {
        "strong": "bold",
        "em": "italic",
        "strike": "strike",
        "underline": "underline",
        "code": "code",
        "subsup": "subscript",  # ADF uses subsup with type attr
    }

    if mark_type in mapping:
        # Handle subsup which has type=sub or type=sup
        if mark_type == "subsup":
            sub_type = attrs.get("type", "sub")
            return {"type": "subscript" if sub_type == "sub" else "superscript"}
        return {"type": mapping[mark_type]}

    if mark_type == "link":
        href = attrs.get("href", "")
        return {"type": "link", "attrs": {"href": href}}

    if mark_type == "textColor":
        color = attrs.get("color", "")
        if color:
            return {"type": "textStyle", "attrs": {"color": color}}

    if mark_type == "backgroundColor":
        color = attrs.get("color", "")
        if color:
            return {"type": "highlight", "attrs": {"color": color}}

    logger.debug("Skipping unsupported ADF mark type: %s", mark_type)
    return None


def _convert_adf_marks(marks: list[dict]) -> list[dict]:
    """Convert ADF marks to TipTap marks."""
    result: list[dict] = []
    for mark in marks:
        converted = _convert_adf_mark(mark)
        if converted:
            result.append(converted)
    return result


# ---------------------------------------------------------------------------
# ADF node -> TipTap node / ImportedBlock
# ---------------------------------------------------------------------------


def _convert_inline_node(node: dict) -> list[dict]:
    """Convert an ADF inline node to TipTap text/inline nodes."""
    node_type = node.get("type", "")

    if node_type == "text":
        text = node.get("text", "")
        marks = _convert_adf_marks(node.get("marks", []))
        return [_text_node(text, marks if marks else None)]

    if node_type == "hardBreak":
        return [{"type": "hardBreak"}]

    if node_type == "emoji":
        attrs = node.get("attrs", {})
        short_name = attrs.get("shortName", "")
        text = attrs.get("text", short_name)
        return [_text_node(text)]

    if node_type == "mention":
        attrs = node.get("attrs", {})
        text = attrs.get("text", "@mention")
        return [_text_node(text, [{"type": "bold"}])]

    if node_type == "inlineCard":
        attrs = node.get("attrs", {})
        url = attrs.get("url", "")
        if url:
            return [_text_node(url, [{"type": "link", "attrs": {"href": url}}])]
        return []

    if node_type == "status":
        attrs = node.get("attrs", {})
        text = attrs.get("text", "")
        return [_text_node(f"[{text}]", [{"type": "bold"}])] if text else []

    if node_type == "date":
        attrs = node.get("attrs", {})
        timestamp = attrs.get("timestamp", "")
        return [_text_node(timestamp)] if timestamp else []

    return []


def _convert_adf_content(content: list[dict]) -> list[dict]:
    """Convert ADF inline content array to TipTap inline nodes."""
    nodes: list[dict] = []
    for child in content:
        nodes.extend(_convert_inline_node(child))
    return nodes


def _convert_adf_block(
    node: dict,
    media: list[ImportedMedia],
    base_url: str = "",
) -> list[ImportedBlock]:
    """Convert a top-level ADF block node to ImportedBlock(s)."""
    node_type = node.get("type", "")
    content = node.get("content", [])
    attrs = node.get("attrs", {})

    # --- Paragraph ---
    if node_type == "paragraph":
        inline = _convert_adf_content(content)
        return [ImportedBlock(block_type="paragraph", content=_paragraph_node(inline))]

    # --- Heading ---
    if node_type == "heading":
        level = attrs.get("level", 1)
        inline = _convert_adf_content(content)
        return [
            ImportedBlock(
                block_type="heading",
                content=_heading_node(level, inline),
                heading_level=level,
            )
        ]

    # --- Bullet list ---
    if node_type == "bulletList":
        items = _convert_list_items(content, media, base_url)
        return [
            ImportedBlock(
                block_type="list",
                content=_bullet_list_node(items),
            )
        ]

    # --- Ordered list ---
    if node_type == "orderedList":
        items = _convert_list_items(content, media, base_url)
        return [
            ImportedBlock(
                block_type="list",
                content=_ordered_list_node(items),
            )
        ]

    # --- Code block ---
    if node_type == "codeBlock":
        language = attrs.get("language", "")
        code_text = ""
        for child in content:
            if child.get("type") == "text":
                code_text += child.get("text", "")
        return [
            ImportedBlock(
                block_type="code",
                content=_code_block_node(code_text, language),
            )
        ]

    # --- Blockquote ---
    if node_type == "blockquote":
        inner: list[dict] = []
        for child in content:
            child_blocks = _convert_adf_block(child, media, base_url)
            for b in child_blocks:
                inner.append(b.content)
        return [
            ImportedBlock(
                block_type="blockquote",
                content=_blockquote_node(inner),
            )
        ]

    # --- Panel (callout equivalent) ---
    if node_type == "panel":
        attrs.get("panelType", "info")
        inner = []
        for child in content:
            child_blocks = _convert_adf_block(child, media, base_url)
            for b in child_blocks:
                inner.append(b.content)
        return [
            ImportedBlock(
                block_type="blockquote",
                content=_blockquote_node(inner),
            )
        ]

    # --- Rule ---
    if node_type == "rule":
        return [
            ImportedBlock(
                block_type="divider",
                content=_horizontal_rule_node(),
            )
        ]

    # --- Table ---
    if node_type == "table":
        rows = _convert_table(content, media, base_url)
        return [ImportedBlock(block_type="table", content=_table_node(rows))]

    # --- Media single / media group ---
    if node_type in ("mediaSingle", "mediaGroup"):
        blocks: list[ImportedBlock] = []
        for child in content:
            if child.get("type") == "media":
                child.get("attrs", {}).get("type", "")
                media_id = child.get("attrs", {}).get("id", "")
                collection = child.get("attrs", {}).get("collection", "")

                # Build attachment URL
                src = ""
                if base_url and media_id:
                    src = (
                        f"{base_url}/wiki/rest/api/content"
                        f"/{collection}/child/attachment"
                        f"/{media_id}/download"
                    )

                alt = child.get("attrs", {}).get("alt", "")
                if src:
                    media.append(
                        ImportedMedia(
                            url=src,
                            file_name=alt or f"confluence-media-{media_id[:8]}",
                            file_type="image/png",
                        )
                    )
                blocks.append(
                    ImportedBlock(
                        block_type="image",
                        content=_image_node(src, alt),
                    )
                )
        return blocks

    # --- Expand ---
    if node_type == "expand":
        expand_title = attrs.get("title", "")
        blocks = []
        if expand_title:
            blocks.append(
                ImportedBlock(
                    block_type="paragraph",
                    content=_paragraph_node([_text_node(expand_title, [{"type": "bold"}])]),
                )
            )
        for child in content:
            blocks.extend(_convert_adf_block(child, media, base_url))
        return blocks

    # --- Layout section / layout column ---
    if node_type in ("layoutSection", "layoutColumn"):
        blocks = []
        for child in content:
            blocks.extend(_convert_adf_block(child, media, base_url))
        return blocks

    # --- Task list ---
    if node_type == "taskList":
        items: list[dict] = []
        for child in content:
            if child.get("type") == "taskItem":
                task_state = child.get("attrs", {}).get("state", "TODO")
                checked = task_state == "DONE"
                inline = _convert_adf_content(child.get("content", []))
                items.append(
                    {
                        "type": "taskItem",
                        "attrs": {"checked": checked},
                        "content": [_paragraph_node(inline)],
                    }
                )
        return [
            ImportedBlock(
                block_type="list",
                content={"type": "taskList", "content": items},
            )
        ]

    # --- Decision list ---
    if node_type == "decisionList":
        blocks = []
        for child in content:
            if child.get("type") == "decisionItem":
                inline = _convert_adf_content(child.get("content", []))
                blocks.append(
                    ImportedBlock(
                        block_type="paragraph",
                        content=_paragraph_node(inline),
                    )
                )
        return blocks

    # --- Bodied extension (macro) ---
    if node_type == "bodiedExtension":
        blocks = []
        for child in content:
            blocks.extend(_convert_adf_block(child, media, base_url))
        return blocks

    # --- Extension (inline macro placeholder) ---
    if node_type == "extension":
        ext_title = attrs.get("extensionTitle", attrs.get("extensionKey", ""))
        if ext_title:
            return [
                ImportedBlock(
                    block_type="paragraph",
                    content=_paragraph_node([_text_node(f"[{ext_title}]", [{"type": "italic"}])]),
                )
            ]
        return []

    logger.debug("Skipping unsupported ADF node type: %s", node_type)
    return []


def _convert_list_items(
    items: list[dict],
    media: list[ImportedMedia],
    base_url: str,
) -> list[dict]:
    """Convert ADF listItem nodes to TipTap listItem nodes."""
    result: list[dict] = []
    for item in items:
        if item.get("type") != "listItem":
            continue
        item_content: list[dict] = []
        for child in item.get("content", []):
            child_blocks = _convert_adf_block(child, media, base_url)
            for b in child_blocks:
                item_content.append(b.content)
        if not item_content:
            item_content.append(_paragraph_node([]))
        result.append(_list_item_node(item_content))
    return result


def _convert_table(
    rows_data: list[dict],
    media: list[ImportedMedia],
    base_url: str,
) -> list[dict]:
    """Convert ADF table rows to TipTap table rows."""
    rows: list[dict] = []
    for row_node in rows_data:
        if row_node.get("type") != "tableRow":
            continue
        cells: list[dict] = []
        for cell_node in row_node.get("content", []):
            cell_type = cell_node.get("type", "tableCell")
            is_header = cell_type == "tableHeader"
            cell_content: list[dict] = []
            for child in cell_node.get("content", []):
                child_blocks = _convert_adf_block(child, media, base_url)
                for b in child_blocks:
                    cell_content.append(b.content)
            if not cell_content:
                cell_content.append(_paragraph_node([]))
            cells.append(_table_cell_node(cell_content, header=is_header))
        rows.append(_table_row_node(cells))
    return rows


# ---------------------------------------------------------------------------
# Confluence API helpers
# ---------------------------------------------------------------------------


async def _fetch_page(
    client: httpx.AsyncClient,
    base_url: str,
    access_token: str,
    page_id: str,
) -> dict:
    """Fetch a Confluence page with ADF body format via REST API v2."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    url = f"{base_url}/wiki/api/v2/pages/{page_id}"
    params = {"body-format": "atlas_doc_format"}

    resp = await client.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def import_from_confluence(
    base_url: str,
    access_token: str,
    page_id: str,
    client: httpx.AsyncClient | None = None,
) -> ImportedDocument:
    """Fetch a Confluence page and convert ADF to an ``ImportedDocument``.

    Parameters:
        base_url: The Confluence instance base URL (e.g. ``https://myorg.atlassian.net``).
        access_token: Atlassian Cloud OAuth access token.
        page_id: The Confluence page ID.
        client: Optional ``httpx.AsyncClient`` for testing / injection.
    """
    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        page_data = await _fetch_page(client, base_url, access_token, page_id)

        title = page_data.get("title", "Untitled")

        # Extract ADF body
        body = page_data.get("body", {})
        adf = body.get("atlas_doc_format", {})
        adf_value = adf.get("value", "{}")

        # ADF value may be a JSON string or already parsed dict
        if isinstance(adf_value, str):
            import json

            adf_doc = json.loads(adf_value)
        else:
            adf_doc = adf_value

        adf_content = adf_doc.get("content", [])

        # Convert ADF blocks
        media: list[ImportedMedia] = []
        blocks: list[ImportedBlock] = []
        for adf_node in adf_content:
            blocks.extend(_convert_adf_block(adf_node, media, base_url))

        # Build source URL
        page_links = page_data.get("_links", {})
        web_ui = page_links.get("webui", "")
        source_url = f"{base_url}/wiki{web_ui}" if web_ui else f"{base_url}/wiki/pages/{page_id}"

        metadata: dict[str, Any] = {
            "confluence_page_id": page_id,
            "confluence_url": source_url,
            "space_id": page_data.get("spaceId"),
        }

        return ImportedDocument(
            title=title,
            blocks=blocks,
            metadata=metadata,
            media=media,
            source_url=source_url,
        )
    finally:
        if should_close:
            await client.aclose()
