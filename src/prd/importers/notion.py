"""Import from Notion API. Converts Notion blocks to TipTap JSON.

Uses Notion API v1 to fetch page content and recursively converts
block types to the TipTap JSON format used by PRD blocks.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

logger = logging.getLogger(__name__)

NOTION_API_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

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
# Notion rich text -> TipTap marks
# ---------------------------------------------------------------------------

_NOTION_COLOR_MAP = {
    "gray": "#787774",
    "brown": "#9F6B53",
    "orange": "#D9730D",
    "yellow": "#CB912F",
    "green": "#448361",
    "blue": "#337EA9",
    "purple": "#9065B0",
    "pink": "#C14C8A",
    "red": "#D44C47",
}


def _rich_text_to_tiptap(rich_text_items: list[dict]) -> list[dict]:
    """Convert Notion rich text array to TipTap text nodes with marks."""
    nodes: list[dict] = []

    for item in rich_text_items:
        text = item.get("plain_text", "")
        if not text:
            continue

        marks: list[dict] = []
        annotations = item.get("annotations", {})

        if annotations.get("bold"):
            marks.append({"type": "bold"})
        if annotations.get("italic"):
            marks.append({"type": "italic"})
        if annotations.get("strikethrough"):
            marks.append({"type": "strike"})
        if annotations.get("underline"):
            marks.append({"type": "underline"})
        if annotations.get("code"):
            marks.append({"type": "code"})

        color = annotations.get("color", "default")
        if color and color != "default":
            if color.endswith("_background"):
                bg_color = _NOTION_COLOR_MAP.get(color.replace("_background", ""))
                if bg_color:
                    marks.append({"type": "highlight", "attrs": {"color": bg_color}})
            else:
                fg_color = _NOTION_COLOR_MAP.get(color)
                if fg_color:
                    marks.append({"type": "textStyle", "attrs": {"color": fg_color}})

        # Link
        href = item.get("href")
        if href:
            marks.append({"type": "link", "attrs": {"href": href}})

        nodes.append(_text_node(text, marks if marks else None))

    return nodes


def _plain_text(rich_text_items: list[dict]) -> str:
    """Extract plain text from Notion rich text array."""
    return "".join(item.get("plain_text", "") for item in rich_text_items)


# ---------------------------------------------------------------------------
# Notion block -> ImportedBlock
# ---------------------------------------------------------------------------


def _convert_block(
    block: dict,
    children_map: dict[str, list[dict]],
    media: list[ImportedMedia],
) -> list[ImportedBlock]:
    """Convert a single Notion block to ImportedBlock(s).

    ``children_map`` holds pre-fetched child blocks keyed by parent block ID.
    """
    block_type = block.get("type", "")
    block_id = block.get("id", "")
    data = block.get(block_type, {})

    # --- Paragraph ---
    if block_type == "paragraph":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        return [ImportedBlock(block_type="paragraph", content=_paragraph_node(content))]

    # --- Headings ---
    if block_type in ("heading_1", "heading_2", "heading_3"):
        level = int(block_type[-1])
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        return [
            ImportedBlock(
                block_type="heading",
                content=_heading_node(level, content),
                heading_level=level,
            )
        ]

    # --- Bulleted list item ---
    if block_type == "bulleted_list_item":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        item_content: list[dict] = [_paragraph_node(content)]

        # Nested children become a nested bullet list
        children = children_map.get(block_id, [])
        if children:
            nested = _convert_list_children(children, children_map, media, ordered=False)
            if nested:
                item_content.append(nested)

        return [
            ImportedBlock(
                block_type="list",
                content=_bullet_list_node([_list_item_node(item_content)]),
            )
        ]

    # --- Numbered list item ---
    if block_type == "numbered_list_item":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        item_content = [_paragraph_node(content)]

        children = children_map.get(block_id, [])
        if children:
            nested = _convert_list_children(children, children_map, media, ordered=True)
            if nested:
                item_content.append(nested)

        return [
            ImportedBlock(
                block_type="list",
                content=_ordered_list_node([_list_item_node(item_content)]),
            )
        ]

    # --- To-do list item ---
    if block_type == "to_do":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        checked = data.get("checked", False)
        return [
            ImportedBlock(
                block_type="list",
                content={
                    "type": "taskList",
                    "content": [
                        {
                            "type": "taskItem",
                            "attrs": {"checked": checked},
                            "content": [_paragraph_node(content)],
                        }
                    ],
                },
            )
        ]

    # --- Code ---
    if block_type == "code":
        code_text = _plain_text(data.get("rich_text", []))
        language = data.get("language", "").lower()
        if language == "plain text":
            language = ""
        return [
            ImportedBlock(
                block_type="code",
                content=_code_block_node(code_text, language),
            )
        ]

    # --- Image ---
    if block_type == "image":
        src = ""
        image_data = data
        if image_data.get("type") == "external":
            src = image_data.get("external", {}).get("url", "")
        elif image_data.get("type") == "file":
            src = image_data.get("file", {}).get("url", "")

        caption_text = _plain_text(image_data.get("caption", []))

        if src:
            media.append(
                ImportedMedia(
                    url=src,
                    file_name=caption_text or f"notion-image-{block_id[:8]}",
                    file_type="image/png",
                )
            )

        return [ImportedBlock(block_type="image", content=_image_node(src, caption_text))]

    # --- Callout ---
    if block_type == "callout":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        icon = data.get("icon", {})
        emoji = icon.get("emoji", "") if icon.get("type") == "emoji" else ""
        # Model callout as a blockquote with icon prefix
        if emoji and content:
            content = [_text_node(f"{emoji} ")] + content
        return [
            ImportedBlock(
                block_type="blockquote",
                content=_blockquote_node([_paragraph_node(content)]),
            )
        ]

    # --- Quote ---
    if block_type == "quote":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        return [
            ImportedBlock(
                block_type="blockquote",
                content=_blockquote_node([_paragraph_node(content)]),
            )
        ]

    # --- Divider ---
    if block_type == "divider":
        return [
            ImportedBlock(
                block_type="divider",
                content=_horizontal_rule_node(),
            )
        ]

    # --- Toggle ---
    if block_type == "toggle":
        content = _rich_text_to_tiptap(data.get("rich_text", []))
        blocks: list[ImportedBlock] = [
            ImportedBlock(
                block_type="paragraph",
                content=_paragraph_node(content),
            )
        ]
        # Expand toggle children
        children = children_map.get(block_id, [])
        for child in children:
            blocks.extend(_convert_block(child, children_map, media))
        return blocks

    # --- Table ---
    if block_type == "table":
        has_column_header = data.get("has_column_header", False)
        children = children_map.get(block_id, [])
        rows: list[dict] = []
        for idx, child in enumerate(children):
            child_data = child.get("table_row", {})
            cells_data = child_data.get("cells", [])
            is_header = has_column_header and idx == 0
            cells = []
            for cell_rich_text in cells_data:
                cell_content = _rich_text_to_tiptap(cell_rich_text)
                cells.append(
                    _table_cell_node(
                        [_paragraph_node(cell_content)],
                        header=is_header,
                    )
                )
            rows.append(_table_row_node(cells))

        return [ImportedBlock(block_type="table", content=_table_node(rows))]

    # --- Bookmark ---
    if block_type == "bookmark":
        url = data.get("url", "")
        caption = _plain_text(data.get("caption", []))
        link_text = caption or url
        if url:
            content = [
                _text_node(
                    link_text,
                    [{"type": "link", "attrs": {"href": url}}],
                )
            ]
        else:
            content = [_text_node(link_text)]
        return [ImportedBlock(block_type="paragraph", content=_paragraph_node(content))]

    # --- Embed ---
    if block_type == "embed":
        url = data.get("url", "")
        if url:
            content = [_text_node(url, [{"type": "link", "attrs": {"href": url}}])]
            return [ImportedBlock(block_type="embed", content=_paragraph_node(content))]
        return []

    # --- Equation ---
    if block_type == "equation":
        expression = data.get("expression", "")
        return [
            ImportedBlock(
                block_type="code",
                content=_code_block_node(expression, "latex"),
            )
        ]

    # --- Column list / Column ---
    if block_type in ("column_list", "column"):
        blocks = []
        children = children_map.get(block_id, [])
        for child in children:
            blocks.extend(_convert_block(child, children_map, media))
        return blocks

    # --- Synced block ---
    if block_type == "synced_block":
        blocks = []
        children = children_map.get(block_id, [])
        for child in children:
            blocks.extend(_convert_block(child, children_map, media))
        return blocks

    # --- Child page / child database ---
    if block_type in ("child_page", "child_database"):
        title_text = data.get("title", block_type)
        return [
            ImportedBlock(
                block_type="paragraph",
                content=_paragraph_node(
                    [_text_node(f"[Linked: {title_text}]", [{"type": "italic"}])]
                ),
            )
        ]

    # --- Fallback: skip unknown blocks ---
    logger.debug("Skipping unsupported Notion block type: %s", block_type)
    return []


def _convert_list_children(
    children: list[dict],
    children_map: dict[str, list[dict]],
    media: list[ImportedMedia],
    ordered: bool,
) -> dict | None:
    """Convert child list items into a nested TipTap list node."""
    items: list[dict] = []
    for child in children:
        child_type = child.get("type", "")
        child_data = child.get(child_type, {})
        child_id = child.get("id", "")

        content = _rich_text_to_tiptap(child_data.get("rich_text", []))
        item_content: list[dict] = [_paragraph_node(content)]

        # Recurse into nested children
        nested_children = children_map.get(child_id, [])
        if nested_children:
            nested = _convert_list_children(nested_children, children_map, media, ordered=ordered)
            if nested:
                item_content.append(nested)

        items.append(_list_item_node(item_content))

    if not items:
        return None

    if ordered:
        return _ordered_list_node(items)
    return _bullet_list_node(items)


# ---------------------------------------------------------------------------
# Notion API helpers
# ---------------------------------------------------------------------------


async def _fetch_page(
    client: httpx.AsyncClient,
    access_token: str,
    page_id: str,
) -> dict:
    """Fetch page metadata from the Notion API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }
    resp = await client.get(
        f"{NOTION_BASE_URL}/pages/{page_id}",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


async def _fetch_blocks(
    client: httpx.AsyncClient,
    access_token: str,
    block_id: str,
) -> list[dict]:
    """Fetch all child blocks for a given block/page, handling pagination."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }

    all_blocks: list[dict] = []
    cursor: str | None = None

    while True:
        params: dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor

        resp = await client.get(
            f"{NOTION_BASE_URL}/blocks/{block_id}/children",
            headers=headers,
            params=params,
        )
        resp.raise_for_status()
        data = resp.json()

        all_blocks.extend(data.get("results", []))

        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    return all_blocks


async def _fetch_blocks_recursive(
    client: httpx.AsyncClient,
    access_token: str,
    block_id: str,
    children_map: dict[str, list[dict]],
    max_depth: int = 5,
    current_depth: int = 0,
) -> list[dict]:
    """Recursively fetch blocks and populate children_map."""
    if current_depth >= max_depth:
        return []

    blocks = await _fetch_blocks(client, access_token, block_id)
    children_map[block_id] = blocks

    for block in blocks:
        if block.get("has_children"):
            child_id = block.get("id", "")
            await _fetch_blocks_recursive(
                client,
                access_token,
                child_id,
                children_map,
                max_depth=max_depth,
                current_depth=current_depth + 1,
            )

    return blocks


def _extract_page_title(page_data: dict) -> str:
    """Extract the page title from Notion page properties."""
    properties = page_data.get("properties", {})

    # The title property can be named anything, but look for type "title"
    for prop_value in properties.values():
        if prop_value.get("type") == "title":
            title_items = prop_value.get("title", [])
            return _plain_text(title_items)

    return "Untitled"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def import_from_notion(
    access_token: str,
    page_id: str,
    client: httpx.AsyncClient | None = None,
) -> ImportedDocument:
    """Fetch a Notion page and convert it to an ``ImportedDocument``.

    Parameters:
        access_token: Notion integration token or OAuth access token.
        page_id: The Notion page ID (UUID with or without dashes).
        client: Optional ``httpx.AsyncClient`` for testing / injection.
    """
    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        # Fetch page metadata
        page_data = await _fetch_page(client, access_token, page_id)
        title = _extract_page_title(page_data)

        # Recursively fetch all blocks
        children_map: dict[str, list[dict]] = {}
        top_blocks = await _fetch_blocks_recursive(client, access_token, page_id, children_map)

        # Convert blocks
        media: list[ImportedMedia] = []
        blocks: list[ImportedBlock] = []
        for block in top_blocks:
            blocks.extend(_convert_block(block, children_map, media))

        # Merge consecutive same-type list items
        blocks = _merge_consecutive_lists(blocks)

        # Build source URL
        clean_id = page_id.replace("-", "")
        source_url = f"https://notion.so/{clean_id}"

        # Extract metadata from page properties
        metadata: dict[str, Any] = {}
        page_url = page_data.get("url")
        if page_url:
            source_url = page_url
            metadata["notion_url"] = page_url

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


def _merge_consecutive_lists(blocks: list[ImportedBlock]) -> list[ImportedBlock]:
    """Merge consecutive list blocks of the same type into a single list.

    Notion returns each list item as a separate block. We merge consecutive
    bulleted or numbered items into a single bulletList/orderedList.
    """
    if not blocks:
        return blocks

    merged: list[ImportedBlock] = []
    i = 0

    while i < len(blocks):
        block = blocks[i]

        if block.block_type == "list" and block.content:
            list_type = block.content.get("type")

            if list_type in ("bulletList", "orderedList"):
                # Accumulate items from consecutive blocks of the same list type
                all_items = list(block.content.get("content", []))
                j = i + 1

                while j < len(blocks):
                    next_block = blocks[j]
                    if (
                        next_block.block_type == "list"
                        and next_block.content
                        and next_block.content.get("type") == list_type
                    ):
                        all_items.extend(next_block.content.get("content", []))
                        j += 1
                    else:
                        break

                merged_content = {"type": list_type, "content": all_items}
                merged.append(ImportedBlock(block_type="list", content=merged_content))
                i = j
                continue

        merged.append(block)
        i += 1

    return merged
