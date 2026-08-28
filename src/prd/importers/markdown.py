"""Convert Markdown to ImportedDocument with TipTap JSON blocks.

Uses ``markdown-it-py`` to parse markdown into an AST then maps AST
nodes to TipTap JSON format. Handles frontmatter (YAML header) as
document metadata.
"""

from __future__ import annotations

import re
from typing import Any

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

# ---------------------------------------------------------------------------
# Frontmatter extraction
# ---------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _extract_frontmatter(content: str) -> tuple[dict, str]:
    """Strip YAML frontmatter from *content* and return (metadata, body).

    If ``pyyaml`` is installed, the frontmatter is parsed into a dict.
    Otherwise the raw string is stored under a ``"raw"`` key.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content

    raw = match.group(1)
    body = content[match.end() :]

    try:
        import yaml

        meta = yaml.safe_load(raw)
        if not isinstance(meta, dict):
            meta = {"raw": raw}
    except Exception:
        meta = {"raw": raw}

    return meta, body


# ---------------------------------------------------------------------------
# TipTap node builders
# ---------------------------------------------------------------------------


def _text_node(text: str, marks: list[dict] | None = None) -> dict:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _heading_node(level: int, content: list[dict]) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": content,
    }


def _paragraph_node(content: list[dict]) -> dict:
    return {"type": "paragraph", "content": content}


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
# Markdown-it AST -> TipTap conversion
# ---------------------------------------------------------------------------


def _collect_inline_content(tokens: list, idx: int) -> list[dict]:
    """Convert inline tokens (children of an inline token) to TipTap text nodes."""
    if idx >= len(tokens):
        return []

    token = tokens[idx]
    if not token.children:
        if token.content:
            return [_text_node(token.content)]
        return []

    nodes: list[dict] = []
    mark_stack: list[dict] = []

    for child in token.children:
        if child.type == "text":
            marks = list(mark_stack) if mark_stack else None
            nodes.append(_text_node(child.content, marks))
        elif child.type == "code_inline":
            marks = [{"type": "code"}]
            if mark_stack:
                marks = list(mark_stack) + marks
            nodes.append(_text_node(child.content, marks))
        elif child.type == "softbreak":
            nodes.append(_text_node("\n"))
        elif child.type == "hardbreak":
            nodes.append({"type": "hardBreak"})
        elif child.type == "image":
            src = child.attrGet("src") or ""
            alt = child.attrGet("alt") or child.content or ""
            nodes.append(_image_node(src, alt))
        elif child.type == "strong_open":
            mark_stack.append({"type": "bold"})
        elif child.type == "strong_close":
            mark_stack = [m for m in mark_stack if m["type"] != "bold"]
        elif child.type == "em_open":
            mark_stack.append({"type": "italic"})
        elif child.type == "em_close":
            mark_stack = [m for m in mark_stack if m["type"] != "italic"]
        elif child.type == "s_open":
            mark_stack.append({"type": "strike"})
        elif child.type == "s_close":
            mark_stack = [m for m in mark_stack if m["type"] != "strike"]
        elif child.type == "link_open":
            href = child.attrGet("href") or ""
            mark_stack.append({"type": "link", "attrs": {"href": href}})
        elif child.type == "link_close":
            mark_stack = [m for m in mark_stack if m["type"] != "link"]
        elif child.type == "html_inline":
            # Inline HTML - treat as plain text
            if child.content:
                marks = list(mark_stack) if mark_stack else None
                nodes.append(_text_node(child.content, marks))

    return nodes


def _tokens_to_blocks(tokens: list) -> list[ImportedBlock]:
    """Walk markdown-it token stream and produce ImportedBlocks."""
    blocks: list[ImportedBlock] = []
    i = 0

    while i < len(tokens):
        tok = tokens[i]

        # --- Heading ---
        if tok.type == "heading_open":
            level = int(tok.tag[1])  # h1 -> 1, h2 -> 2, etc.
            inline_content = _collect_inline_content(tokens, i + 1)
            content = _heading_node(level, inline_content)
            blocks.append(
                ImportedBlock(
                    block_type="heading",
                    content=content,
                    heading_level=level,
                )
            )
            i += 3  # heading_open, inline, heading_close
            continue

        # --- Paragraph ---
        if tok.type == "paragraph_open":
            inline_content = _collect_inline_content(tokens, i + 1)
            # Check if the paragraph is just an image
            if (
                len(inline_content) == 1
                and isinstance(inline_content[0], dict)
                and inline_content[0].get("type") == "image"
            ):
                img = inline_content[0]
                src = img.get("attrs", {}).get("src", "")
                alt = img.get("attrs", {}).get("alt", "")
                blocks.append(
                    ImportedBlock(
                        block_type="image",
                        content=_image_node(src, alt),
                    )
                )
            else:
                content = _paragraph_node(inline_content)
                blocks.append(ImportedBlock(block_type="paragraph", content=content))
            i += 3  # paragraph_open, inline, paragraph_close
            continue

        # --- Code block (fenced or indented) ---
        if tok.type in ("fence", "code_block"):
            language = tok.info.strip() if tok.info else ""
            code = tok.content
            # Strip trailing newline that markdown-it adds
            if code.endswith("\n"):
                code = code[:-1]
            content = _code_block_node(code, language)
            blocks.append(ImportedBlock(block_type="code", content=content))
            i += 1
            continue

        # --- Horizontal rule ---
        if tok.type == "hr":
            blocks.append(
                ImportedBlock(
                    block_type="divider",
                    content=_horizontal_rule_node(),
                )
            )
            i += 1
            continue

        # --- Blockquote ---
        if tok.type == "blockquote_open":
            # Gather tokens until blockquote_close at same nesting
            nesting = 1
            inner_tokens = []
            j = i + 1
            while j < len(tokens):
                if tokens[j].type == "blockquote_open":
                    nesting += 1
                elif tokens[j].type == "blockquote_close":
                    nesting -= 1
                    if nesting == 0:
                        break
                inner_tokens.append(tokens[j])
                j += 1

            inner_blocks = _tokens_to_blocks(inner_tokens)
            # Wrap inner block content into blockquote TipTap node
            bq_content = [b.content for b in inner_blocks if b.content]
            content = _blockquote_node(bq_content)
            blocks.append(ImportedBlock(block_type="blockquote", content=content))
            i = j + 1
            continue

        # --- Bullet list ---
        if tok.type == "bullet_list_open":
            items, end_idx = _parse_list(tokens, i, ordered=False)
            content = _bullet_list_node(items)
            blocks.append(ImportedBlock(block_type="list", content=content))
            i = end_idx + 1
            continue

        # --- Ordered list ---
        if tok.type == "ordered_list_open":
            items, end_idx = _parse_list(tokens, i, ordered=True)
            content = _ordered_list_node(items)
            blocks.append(ImportedBlock(block_type="list", content=content))
            i = end_idx + 1
            continue

        # --- HTML block ---
        if tok.type == "html_block":
            if tok.content.strip():
                content = _paragraph_node([_text_node(tok.content.strip())])
                blocks.append(ImportedBlock(block_type="paragraph", content=content))
            i += 1
            continue

        # --- Table ---
        if tok.type == "table_open":
            rows, end_idx = _parse_table(tokens, i)
            content = _table_node(rows)
            blocks.append(ImportedBlock(block_type="table", content=content))
            i = end_idx + 1
            continue

        # Skip unhandled tokens
        i += 1

    return blocks


def _parse_list(tokens: list, start: int, ordered: bool) -> tuple[list[dict], int]:
    """Parse list tokens from *start* and return (list_items, close_index)."""
    close_type = "ordered_list_close" if ordered else "bullet_list_close"
    items: list[dict] = []
    i = start + 1

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == close_type:
            return items, i

        if tok.type == "list_item_open":
            item_content, end_idx = _parse_list_item(tokens, i)
            items.append(_list_item_node(item_content))
            i = end_idx + 1
            continue

        i += 1

    return items, len(tokens) - 1


def _parse_list_item(tokens: list, start: int) -> tuple[list[dict], int]:
    """Parse a single list_item and return (content_nodes, close_index)."""
    content: list[dict] = []
    i = start + 1

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "list_item_close":
            return content, i

        if tok.type == "paragraph_open":
            inline_content = _collect_inline_content(tokens, i + 1)
            content.append(_paragraph_node(inline_content))
            i += 3
            continue

        # Nested bullet list
        if tok.type == "bullet_list_open":
            items, end_idx = _parse_list(tokens, i, ordered=False)
            content.append(_bullet_list_node(items))
            i = end_idx + 1
            continue

        # Nested ordered list
        if tok.type == "ordered_list_open":
            items, end_idx = _parse_list(tokens, i, ordered=True)
            content.append(_ordered_list_node(items))
            i = end_idx + 1
            continue

        i += 1

    return content, len(tokens) - 1


def _parse_table(tokens: list, start: int) -> tuple[list[dict], int]:
    """Parse table tokens and return (rows, close_index)."""
    rows: list[dict] = []
    i = start + 1
    in_header = False

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "table_close":
            return rows, i

        if tok.type == "thead_open":
            in_header = True
            i += 1
            continue
        if tok.type == "thead_close":
            in_header = False
            i += 1
            continue
        if tok.type in ("tbody_open", "tbody_close"):
            i += 1
            continue

        if tok.type == "tr_open":
            cells, end_idx = _parse_table_row(tokens, i, is_header=in_header)
            rows.append(_table_row_node(cells))
            i = end_idx + 1
            continue

        i += 1

    return rows, len(tokens) - 1


def _parse_table_row(tokens: list, start: int, is_header: bool) -> tuple[list[dict], int]:
    """Parse a table row and return (cells, close_index)."""
    cells: list[dict] = []
    i = start + 1

    while i < len(tokens):
        tok = tokens[i]

        if tok.type == "tr_close":
            return cells, i

        if tok.type in ("th_open", "td_open"):
            inline_content = _collect_inline_content(tokens, i + 1)
            cell_content = (
                [_paragraph_node(inline_content)] if inline_content else [_paragraph_node([])]
            )
            cells.append(_table_cell_node(cell_content, header=is_header))
            i += 3  # open, inline, close
            continue

        i += 1

    return cells, len(tokens) - 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def import_markdown(
    content: str,
    title: str | None = None,
) -> ImportedDocument:
    """Parse a markdown string to an ``ImportedDocument``.

    If no *title* is given, the first ``# heading`` in the document is
    used. Failing that, falls back to ``"Untitled Document"``.
    """
    from markdown_it import MarkdownIt

    metadata, body = _extract_frontmatter(content)

    # Enable tables and strikethrough
    md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
    tokens = md.parse(body)

    blocks = _tokens_to_blocks(tokens)

    # Collect media references from image blocks
    media: list[ImportedMedia] = []
    for block in blocks:
        if block.block_type == "image":
            src = block.content.get("attrs", {}).get("src", "")
            alt = block.content.get("attrs", {}).get("alt", "")
            if src and src.startswith(("http://", "https://")):
                media.append(
                    ImportedMedia(
                        url=src,
                        file_name=alt or src.split("/")[-1].split("?")[0] or "image",
                        file_type="image/png",
                    )
                )

    # Derive title
    if not title:
        title = metadata.get("title")
    if not title:
        for block in blocks:
            if block.block_type == "heading" and block.heading_level == 1:
                # Extract text from heading content
                for node in block.content.get("content", []):
                    if node.get("type") == "text":
                        title = node.get("text", "")
                        break
                if title:
                    break
    if not title:
        title = "Untitled Document"

    # Merge frontmatter metadata with tags
    tags = metadata.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not isinstance(tags, list):
        tags = []

    doc_metadata = dict(metadata)
    doc_metadata["tags"] = tags

    return ImportedDocument(
        title=title,
        blocks=blocks,
        metadata=doc_metadata,
        media=media,
    )
