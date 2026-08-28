"""Import from Google Docs API. Converts structured elements to TipTap JSON.

Maps Google Docs structural elements, paragraph styles, text runs, and
inline objects to the TipTap JSON format used by PRD blocks.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

logger = logging.getLogger(__name__)

DOCS_API_URL = "https://docs.googleapis.com/v1/documents"

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
# Google Docs text style -> TipTap marks
# ---------------------------------------------------------------------------

_HEADING_STYLE_MAP = {
    "HEADING_1": 1,
    "HEADING_2": 2,
    "HEADING_3": 3,
    "HEADING_4": 4,
    "HEADING_5": 5,
    "HEADING_6": 6,
    "TITLE": 1,
    "SUBTITLE": 2,
}


def _text_style_to_marks(text_style: dict) -> list[dict]:
    """Convert Google Docs TextStyle to TipTap marks."""
    marks: list[dict] = []

    if text_style.get("bold"):
        marks.append({"type": "bold"})
    if text_style.get("italic"):
        marks.append({"type": "italic"})
    if text_style.get("underline"):
        marks.append({"type": "underline"})
    if text_style.get("strikethrough"):
        marks.append({"type": "strike"})
    if text_style.get("baselineOffset") == "SUPERSCRIPT":
        marks.append({"type": "superscript"})
    if text_style.get("baselineOffset") == "SUBSCRIPT":
        marks.append({"type": "subscript"})

    # Link
    link = text_style.get("link", {})
    url = link.get("url", "")
    if url:
        marks.append({"type": "link", "attrs": {"href": url}})

    # Font color (skip default black)
    fg_color = text_style.get("foregroundColor", {}).get("color", {}).get("rgbColor", {})
    if fg_color and fg_color != {"red": 0, "green": 0, "blue": 0}:
        r = int(fg_color.get("red", 0) * 255)
        g = int(fg_color.get("green", 0) * 255)
        b = int(fg_color.get("blue", 0) * 255)
        # Only add color mark if it's not pure black
        if r + g + b > 0:
            marks.append({"type": "textStyle", "attrs": {"color": f"rgb({r},{g},{b})"}})

    return marks


# ---------------------------------------------------------------------------
# Element conversion
# ---------------------------------------------------------------------------


def _convert_text_run(text_run: dict) -> list[dict]:
    """Convert a Google Docs TextRun to TipTap text nodes."""
    content = text_run.get("content", "")
    if not content or content == "\n":
        return []

    # Strip trailing newline (Google Docs paragraphs end with \n)
    if content.endswith("\n"):
        content = content[:-1]
    if not content:
        return []

    text_style = text_run.get("textStyle", {})
    marks = _text_style_to_marks(text_style)
    return [_text_node(content, marks if marks else None)]


def _convert_paragraph_elements(
    elements: list[dict],
    inline_objects: dict,
    media: list[ImportedMedia],
) -> list[dict]:
    """Convert a list of Google Docs paragraph elements to TipTap inline nodes."""
    nodes: list[dict] = []

    for element in elements:
        # Text run
        text_run = element.get("textRun")
        if text_run:
            nodes.extend(_convert_text_run(text_run))
            continue

        # Inline object (image)
        inline_obj_element = element.get("inlineObjectElement")
        if inline_obj_element:
            obj_id = inline_obj_element.get("inlineObjectId", "")
            obj_data = inline_objects.get(obj_id, {})
            obj_props = obj_data.get("inlineObjectProperties", {})
            embedded = obj_props.get("embeddedObject", {})

            # Get image URL
            image_props = embedded.get("imageProperties", {})
            source_uri = image_props.get("sourceUri") or image_props.get("contentUri", "")

            # Alternative: check for content URI from the embedded object
            if not source_uri:
                source_uri = embedded.get("imageProperties", {}).get("contentUri", "")

            title = embedded.get("title", "")
            description = embedded.get("description", title)

            if source_uri:
                media.append(
                    ImportedMedia(
                        url=source_uri,
                        file_name=description or f"gdocs-image-{obj_id[:8]}",
                        file_type="image/png",
                    )
                )
                nodes.append(_image_node(source_uri, description))
            continue

        # Horizontal rule element
        if element.get("horizontalRule"):
            nodes.append({"type": "horizontalRule"})
            continue

        # Auto text (page number, etc.) - skip
        if element.get("autoText"):
            continue

        # Page break - skip
        if element.get("pageBreak"):
            continue

        # Equation
        equation = element.get("equation")
        if equation:
            nodes.append(_text_node("[equation]", [{"type": "code"}]))
            continue

    return nodes


def _convert_paragraph(
    paragraph: dict,
    inline_objects: dict,
    media: list[ImportedMedia],
) -> ImportedBlock | None:
    """Convert a Google Docs paragraph element to an ImportedBlock."""
    paragraph_style = paragraph.get("paragraphStyle", {})
    named_style = paragraph_style.get("namedStyleType", "NORMAL_TEXT")
    elements = paragraph.get("elements", [])

    inline_nodes = _convert_paragraph_elements(elements, inline_objects, media)

    # Check if this is just a horizontal rule
    if (
        len(inline_nodes) == 1
        and isinstance(inline_nodes[0], dict)
        and inline_nodes[0].get("type") == "horizontalRule"
    ):
        return ImportedBlock(block_type="divider", content=_horizontal_rule_node())

    # Check if this paragraph is just an image
    if (
        len(inline_nodes) == 1
        and isinstance(inline_nodes[0], dict)
        and inline_nodes[0].get("type") == "image"
    ):
        return ImportedBlock(block_type="image", content=inline_nodes[0])

    if not inline_nodes:
        return None

    # Heading
    if named_style in _HEADING_STYLE_MAP:
        level = _HEADING_STYLE_MAP[named_style]
        return ImportedBlock(
            block_type="heading",
            content=_heading_node(level, inline_nodes),
            heading_level=level,
        )

    # Regular paragraph
    return ImportedBlock(
        block_type="paragraph",
        content=_paragraph_node(inline_nodes),
    )


def _convert_table(
    table: dict,
    inline_objects: dict,
    media: list[ImportedMedia],
) -> ImportedBlock:
    """Convert a Google Docs Table element to an ImportedBlock."""
    rows_data = table.get("tableRows", [])
    rows: list[dict] = []

    for row_idx, row in enumerate(rows_data):
        cells: list[dict] = []
        is_header = row_idx == 0  # Treat first row as header

        for cell in row.get("tableCells", []):
            cell_content: list[dict] = []
            for content_item in cell.get("content", []):
                para = content_item.get("paragraph")
                if para:
                    block = _convert_paragraph(para, inline_objects, media)
                    if block:
                        cell_content.append(block.content)

            if not cell_content:
                cell_content.append(_paragraph_node([]))

            cells.append(_table_cell_node(cell_content, header=is_header))

        rows.append(_table_row_node(cells))

    return ImportedBlock(block_type="table", content=_table_node(rows))


def _convert_section_break() -> ImportedBlock:
    """Convert a Google Docs section break to a horizontal rule."""
    return ImportedBlock(block_type="divider", content=_horizontal_rule_node())


# ---------------------------------------------------------------------------
# List handling
# ---------------------------------------------------------------------------


def _get_list_type(
    lists: dict,
    list_id: str,
    nesting_level: int,
) -> str:
    """Determine if a list is ordered or unordered from the document's lists metadata."""
    list_data = lists.get(list_id, {})
    nesting_levels = list_data.get("listProperties", {}).get("nestingLevels", [])

    if nesting_level < len(nesting_levels):
        level_props = nesting_levels[nesting_level]
        glyph_type = level_props.get("glyphType", "")
        glyph_symbol = level_props.get("glyphSymbol", "")

        # Ordered if glyph_type is set (DECIMAL, ALPHA, ROMAN, etc.)
        if glyph_type and glyph_type != "GLYPH_TYPE_UNSPECIFIED":
            return "ordered"

        # Unordered if glyph_symbol is set (bullet chars)
        if glyph_symbol:
            return "unordered"

    return "unordered"  # Default to unordered


def _group_list_items(
    blocks: list[ImportedBlock],
    raw_paragraphs: list[dict],
    lists: dict,
) -> list[ImportedBlock]:
    """Post-process blocks to group consecutive list paragraphs into list blocks.

    Google Docs represents lists as paragraphs with a ``bullet`` property. We
    need to group consecutive list paragraphs at the same nesting level.
    """
    if len(blocks) != len(raw_paragraphs):
        return blocks

    result: list[ImportedBlock] = []
    i = 0

    while i < len(blocks):
        bullet = raw_paragraphs[i].get("bullet")
        if not bullet:
            result.append(blocks[i])
            i += 1
            continue

        # Start collecting list items
        list_id = bullet.get("listId", "")
        nesting_level = bullet.get("nestingLevel", 0)
        list_type = _get_list_type(lists, list_id, nesting_level)

        items: list[dict] = []
        while i < len(blocks):
            b = raw_paragraphs[i].get("bullet")
            if not b or b.get("listId") != list_id:
                break

            current_nesting = b.get("nestingLevel", 0)
            if current_nesting != nesting_level:
                # Different nesting - treat as part of current list but indented
                # For simplicity, flatten nested levels
                pass

            block_content = blocks[i].content
            items.append(_list_item_node([block_content]))
            i += 1

        if list_type == "ordered":
            list_content = _ordered_list_node(items)
        else:
            list_content = _bullet_list_node(items)

        result.append(ImportedBlock(block_type="list", content=list_content))

    return result


# ---------------------------------------------------------------------------
# Google Docs API helper
# ---------------------------------------------------------------------------


async def _fetch_document(
    client: httpx.AsyncClient,
    access_token: str,
    document_id: str,
) -> dict:
    """Fetch a Google Doc via the Docs API."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    resp = await client.get(
        f"{DOCS_API_URL}/{document_id}",
        headers=headers,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def import_from_google_docs(
    access_token: str,
    document_id: str,
    client: httpx.AsyncClient | None = None,
) -> ImportedDocument:
    """Fetch a Google Doc and convert it to an ``ImportedDocument``.

    Parameters:
        access_token: Google OAuth access token with docs.readonly scope.
        document_id: The Google Docs document ID.
        client: Optional ``httpx.AsyncClient`` for testing / injection.
    """
    should_close = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=30.0)

    try:
        doc_data = await _fetch_document(client, access_token, document_id)

        title = doc_data.get("title", "Untitled")
        body = doc_data.get("body", {})
        content_elements = body.get("content", [])
        inline_objects = doc_data.get("inlineObjects", {})
        lists = doc_data.get("lists", {})

        media: list[ImportedMedia] = []
        blocks: list[ImportedBlock] = []
        raw_paragraphs: list[dict] = []

        for element in content_elements:
            # Paragraph
            paragraph = element.get("paragraph")
            if paragraph:
                block = _convert_paragraph(paragraph, inline_objects, media)
                if block:
                    blocks.append(block)
                    raw_paragraphs.append(paragraph)
                continue

            # Table
            table = element.get("table")
            if table:
                block = _convert_table(table, inline_objects, media)
                blocks.append(block)
                raw_paragraphs.append({})  # placeholder
                continue

            # Section break
            if element.get("sectionBreak"):
                # Only add section breaks between content, not at start
                if blocks:
                    blocks.append(_convert_section_break())
                    raw_paragraphs.append({})
                continue

            # Table of contents
            toc = element.get("tableOfContents")
            if toc:
                toc_content = toc.get("content", [])
                for toc_el in toc_content:
                    para = toc_el.get("paragraph")
                    if para:
                        block = _convert_paragraph(para, inline_objects, media)
                        if block:
                            blocks.append(block)
                            raw_paragraphs.append(para)
                continue

        # Group list items
        blocks = _group_list_items(blocks, raw_paragraphs, lists)

        # Build source URL
        source_url = f"https://docs.google.com/document/d/{document_id}/edit"

        metadata: dict[str, Any] = {
            "google_docs_id": document_id,
            "google_docs_url": source_url,
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
