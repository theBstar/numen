"""Convert HTML to ImportedDocument with TipTap JSON blocks.

Uses BeautifulSoup4 to parse HTML and maps elements to TipTap JSON
nodes that can be stored as PRD blocks.
"""

from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup, NavigableString, Tag

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

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
# Inline element conversion
# ---------------------------------------------------------------------------

_INLINE_TAGS = {
    "strong": "bold",
    "b": "bold",
    "em": "italic",
    "i": "italic",
    "u": "underline",
    "s": "strike",
    "del": "strike",
    "strike": "strike",
    "code": "code",
    "sub": "subscript",
    "sup": "superscript",
}


def _convert_inline(element: Tag | NavigableString, marks: list[dict] | None = None) -> list[dict]:
    """Recursively convert an inline HTML element to TipTap text nodes with marks."""
    if marks is None:
        marks = []

    if isinstance(element, NavigableString):
        text = str(element)
        if not text:
            return []
        return [_text_node(text, list(marks) if marks else None)]

    if not isinstance(element, Tag):
        return []

    tag_name = element.name.lower()

    # Links
    if tag_name == "a":
        href = element.get("href", "")
        new_marks = list(marks) + [{"type": "link", "attrs": {"href": href}}]
        nodes: list[dict] = []
        for child in element.children:
            nodes.extend(_convert_inline(child, new_marks))
        return nodes

    # Inline marks (bold, italic, code, etc.)
    if tag_name in _INLINE_TAGS:
        mark_type = _INLINE_TAGS[tag_name]
        new_marks = list(marks) + [{"type": mark_type}]
        nodes = []
        for child in element.children:
            nodes.extend(_convert_inline(child, new_marks))
        return nodes

    # <br> -> newline
    if tag_name == "br":
        return [{"type": "hardBreak"}]

    # <img> inline
    if tag_name == "img":
        src = element.get("src", "")
        alt = element.get("alt", "")
        return [_image_node(str(src), str(alt))]

    # <span> and other inline wrappers - pass through
    if tag_name in ("span", "mark", "abbr", "cite", "q", "small", "time"):
        nodes = []
        for child in element.children:
            nodes.extend(_convert_inline(child, marks))
        return nodes

    # Fallback: try converting children
    nodes = []
    for child in element.children:
        nodes.extend(_convert_inline(child, marks))
    return nodes


def _get_inline_content(element: Tag) -> list[dict]:
    """Extract inline content from a block-level element."""
    nodes: list[dict] = []
    for child in element.children:
        nodes.extend(_convert_inline(child))
    return nodes


# ---------------------------------------------------------------------------
# Block element conversion
# ---------------------------------------------------------------------------

_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}


def _convert_list(element: Tag, ordered: bool) -> ImportedBlock:
    """Convert a <ul> or <ol> to a TipTap list block."""
    items: list[dict] = []
    for li in element.find_all("li", recursive=False):
        item_content: list[dict] = []

        # Gather inline text of this <li> (excluding nested lists)
        inline_parts: list[dict] = []
        for child in li.children:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                # Flush inline text as paragraph before nested list
                if inline_parts:
                    item_content.append(_paragraph_node(inline_parts))
                    inline_parts = []
                # Nested list
                nested_ordered = child.name == "ol"
                nested_items = _convert_list_items(child, nested_ordered)
                if nested_ordered:
                    item_content.append(_ordered_list_node(nested_items))
                else:
                    item_content.append(_bullet_list_node(nested_items))
            else:
                inline_parts.extend(_convert_inline(child))

        if inline_parts:
            item_content.append(_paragraph_node(inline_parts))

        if not item_content:
            item_content.append(_paragraph_node([]))

        items.append(_list_item_node(item_content))

    if ordered:
        content = _ordered_list_node(items)
    else:
        content = _bullet_list_node(items)

    return ImportedBlock(block_type="list", content=content)


def _convert_list_items(element: Tag, ordered: bool) -> list[dict]:
    """Convert child <li> elements to TipTap list item nodes."""
    items: list[dict] = []
    for li in element.find_all("li", recursive=False):
        item_content: list[dict] = []
        inline_parts: list[dict] = []

        for child in li.children:
            if isinstance(child, Tag) and child.name in ("ul", "ol"):
                if inline_parts:
                    item_content.append(_paragraph_node(inline_parts))
                    inline_parts = []
                nested_ordered = child.name == "ol"
                nested_items = _convert_list_items(child, nested_ordered)
                if nested_ordered:
                    item_content.append(_ordered_list_node(nested_items))
                else:
                    item_content.append(_bullet_list_node(nested_items))
            else:
                inline_parts.extend(_convert_inline(child))

        if inline_parts:
            item_content.append(_paragraph_node(inline_parts))
        if not item_content:
            item_content.append(_paragraph_node([]))

        items.append(_list_item_node(item_content))

    return items


def _convert_table(element: Tag) -> ImportedBlock:
    """Convert a <table> element to a TipTap table block."""
    rows: list[dict] = []

    # Process <thead>
    thead = element.find("thead")
    if thead and isinstance(thead, Tag):
        for tr in thead.find_all("tr", recursive=False):
            cells = _convert_table_row(tr, is_header=True)
            rows.append(_table_row_node(cells))

    # Process <tbody> (or direct <tr> children)
    tbody = element.find("tbody")
    row_parent = tbody if (tbody and isinstance(tbody, Tag)) else element
    for tr in row_parent.find_all("tr", recursive=False):
        # Skip rows already added from thead
        if thead and isinstance(thead, Tag) and tr.parent == thead:
            continue
        cells = _convert_table_row(tr, is_header=False)
        rows.append(_table_row_node(cells))

    return ImportedBlock(block_type="table", content=_table_node(rows))


def _convert_table_row(tr: Tag, is_header: bool) -> list[dict]:
    """Convert a <tr> to a list of TipTap cell nodes."""
    cells: list[dict] = []
    for cell in tr.find_all(["th", "td"], recursive=False):
        cell_is_header = is_header or cell.name == "th"
        inline = _get_inline_content(cell)
        cell_content = [_paragraph_node(inline)] if inline else [_paragraph_node([])]
        cells.append(_table_cell_node(cell_content, header=cell_is_header))
    return cells


def _convert_blockquote(element: Tag) -> ImportedBlock:
    """Convert a <blockquote> to TipTap blockquote block."""
    inner_content: list[dict] = []

    for child in element.children:
        if isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                inner_content.append(_paragraph_node([_text_node(text)]))
        elif isinstance(child, Tag):
            tag_name = child.name.lower()
            if tag_name in _HEADING_TAGS:
                level = _HEADING_TAGS[tag_name]
                inner_content.append(_heading_node(level, _get_inline_content(child)))
            elif tag_name == "p":
                inner_content.append(_paragraph_node(_get_inline_content(child)))
            else:
                inline = _get_inline_content(child)
                if inline:
                    inner_content.append(_paragraph_node(inline))

    if not inner_content:
        inner_content.append(_paragraph_node([]))

    return ImportedBlock(
        block_type="blockquote",
        content=_blockquote_node(inner_content),
    )


def _convert_element(element: Tag) -> list[ImportedBlock]:
    """Convert a single block-level HTML element to ImportedBlock(s)."""
    tag_name = element.name.lower()

    # Headings
    if tag_name in _HEADING_TAGS:
        level = _HEADING_TAGS[tag_name]
        inline = _get_inline_content(element)
        return [
            ImportedBlock(
                block_type="heading",
                content=_heading_node(level, inline),
                heading_level=level,
            )
        ]

    # Paragraph
    if tag_name == "p":
        inline = _get_inline_content(element)
        # Check if paragraph contains only an image
        if len(inline) == 1 and isinstance(inline[0], dict) and inline[0].get("type") == "image":
            return [ImportedBlock(block_type="image", content=inline[0])]
        return [ImportedBlock(block_type="paragraph", content=_paragraph_node(inline))]

    # Code blocks
    if tag_name == "pre":
        code_el = element.find("code")
        if code_el and isinstance(code_el, Tag):
            code = code_el.get_text()
            # Try to extract language from class="language-xxx"
            language = ""
            classes = code_el.get("class", [])
            if isinstance(classes, list):
                for cls in classes:
                    if isinstance(cls, str) and cls.startswith("language-"):
                        language = cls[9:]
                        break
            return [
                ImportedBlock(
                    block_type="code",
                    content=_code_block_node(code, language),
                )
            ]
        # Pre without code child
        return [
            ImportedBlock(
                block_type="code",
                content=_code_block_node(element.get_text()),
            )
        ]

    # Lists
    if tag_name == "ul":
        return [_convert_list(element, ordered=False)]
    if tag_name == "ol":
        return [_convert_list(element, ordered=True)]

    # Blockquote
    if tag_name == "blockquote":
        return [_convert_blockquote(element)]

    # Horizontal rule
    if tag_name == "hr":
        return [
            ImportedBlock(
                block_type="divider",
                content=_horizontal_rule_node(),
            )
        ]

    # Images
    if tag_name == "img":
        src = str(element.get("src", ""))
        alt = str(element.get("alt", ""))
        return [ImportedBlock(block_type="image", content=_image_node(src, alt))]

    # Figure (wraps image + caption)
    if tag_name == "figure":
        blocks: list[ImportedBlock] = []
        img = element.find("img")
        if img and isinstance(img, Tag):
            src = str(img.get("src", ""))
            alt = str(img.get("alt", ""))
            blocks.append(ImportedBlock(block_type="image", content=_image_node(src, alt)))
        caption = element.find("figcaption")
        if caption and isinstance(caption, Tag):
            inline = _get_inline_content(caption)
            if inline:
                blocks.append(
                    ImportedBlock(block_type="paragraph", content=_paragraph_node(inline))
                )
        return blocks

    # Table
    if tag_name == "table":
        return [_convert_table(element)]

    # Div, section, article, main, aside - recurse into children
    if tag_name in (
        "div",
        "section",
        "article",
        "main",
        "aside",
        "header",
        "footer",
        "nav",
        "details",
        "summary",
    ):
        blocks = []
        for child in element.children:
            if isinstance(child, Tag):
                blocks.extend(_convert_element(child))
            elif isinstance(child, NavigableString):
                text = str(child).strip()
                if text:
                    blocks.append(
                        ImportedBlock(
                            block_type="paragraph",
                            content=_paragraph_node([_text_node(text)]),
                        )
                    )
        return blocks

    # Fallback: convert inline content as paragraph
    inline = _get_inline_content(element)
    if inline:
        return [ImportedBlock(block_type="paragraph", content=_paragraph_node(inline))]

    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_html(
    html_content: str,
    title: str | None = None,
) -> ImportedDocument:
    """Parse an HTML string to an ``ImportedDocument``.

    If no *title* is given, ``<title>`` or the first ``<h1>`` is used.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # Try to extract title
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Find the main content area
    body = soup.find("body") or soup

    # Convert block elements
    blocks: list[ImportedBlock] = []
    for child in body.children:
        if isinstance(child, Tag):
            # Skip script, style, meta tags
            if child.name in ("script", "style", "meta", "link", "noscript", "title", "head"):
                continue
            blocks.extend(_convert_element(child))
        elif isinstance(child, NavigableString):
            text = str(child).strip()
            if text:
                blocks.append(
                    ImportedBlock(
                        block_type="paragraph",
                        content=_paragraph_node([_text_node(text)]),
                    )
                )

    # Fall back title from first h1
    if not title:
        for block in blocks:
            if block.block_type == "heading" and block.heading_level == 1:
                for node in block.content.get("content", []):
                    if node.get("type") == "text":
                        title = node.get("text", "")
                        break
                if title:
                    break

    if not title:
        title = "Untitled Document"

    # Collect media
    media: list[ImportedMedia] = []
    for block in blocks:
        if block.block_type == "image":
            src = block.content.get("attrs", {}).get("src", "")
            alt = block.content.get("attrs", {}).get("alt", "")
            if src and src.startswith(("http://", "https://")):
                ext = src.split(".")[-1].split("?")[0].lower()
                file_type_map = {
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "gif": "image/gif",
                    "webp": "image/webp",
                    "svg": "image/svg+xml",
                }
                file_type = file_type_map.get(ext, "image/png")
                media.append(
                    ImportedMedia(
                        url=src,
                        file_name=alt or src.split("/")[-1].split("?")[0] or "image",
                        file_type=file_type,
                    )
                )

    return ImportedDocument(
        title=title,
        blocks=blocks,
        metadata={},
        media=media,
    )
