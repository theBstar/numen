"""Markdown exporter - convert TipTap JSON blocks to Markdown string.

Pure function with no side effects. Handles all TipTap node types
including headings, paragraphs, lists, tables, code blocks, images,
blockquotes, horizontal rules, and task lists. Inline marks are
converted to their Markdown equivalents.
"""

from __future__ import annotations


def export_to_markdown(
    title: str,
    blocks: list[dict],
    metadata: dict | None = None,
) -> str:
    """Convert TipTap JSON blocks to a Markdown string.

    Args:
        title: Document title.
        blocks: List of TipTap block dicts (each with block_type, content, heading_level).
        metadata: Optional dict with keys like status, owner, tags, target_date, description.

    Returns:
        Complete Markdown document as a string.
    """
    parts: list[str] = []

    # Optional YAML frontmatter
    if metadata:
        parts.append(_build_frontmatter(title, metadata))
    else:
        parts.append(f"# {title}\n")

    for block in blocks:
        content = block.get("content", {})
        block_type = block.get("block_type", "paragraph")
        heading_level = block.get("heading_level")

        md = _render_block(block_type, content, heading_level)
        if md is not None:
            parts.append(md)

    return "\n".join(parts).rstrip() + "\n"


# ── Frontmatter ──────────────────────────────────────────────────────


def _build_frontmatter(title: str, metadata: dict) -> str:
    """Build YAML frontmatter block."""
    lines = ["---", f'title: "{title}"']

    if metadata.get("status"):
        lines.append(f"status: {metadata['status']}")
    if metadata.get("owner"):
        lines.append(f'owner: "{metadata["owner"]}"')
    if metadata.get("priority"):
        lines.append(f"priority: {metadata['priority']}")
    if metadata.get("target_date"):
        lines.append(f"target_date: {metadata['target_date']}")
    if metadata.get("tags"):
        tag_list = ", ".join(metadata["tags"])
        lines.append(f"tags: [{tag_list}]")
    if metadata.get("description"):
        lines.append(f'description: "{metadata["description"]}"')

    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    return "\n".join(lines)


# ── Block rendering ──────────────────────────────────────────────────


def _render_block(
    block_type: str,
    content: dict,
    heading_level: int | None = None,
) -> str | None:
    """Render a single TipTap block to Markdown."""
    if block_type == "heading":
        return _render_heading(content, heading_level)
    elif block_type == "paragraph":
        return _render_paragraph(content)
    elif block_type == "codeBlock":
        return _render_code_block(content)
    elif block_type == "bulletList":
        return _render_bullet_list(content)
    elif block_type == "orderedList":
        return _render_ordered_list(content)
    elif block_type == "taskList":
        return _render_task_list(content)
    elif block_type == "blockquote":
        return _render_blockquote(content)
    elif block_type == "image":
        return _render_image(content)
    elif block_type == "horizontalRule":
        return "\n---\n"
    elif block_type == "table":
        return _render_table(content)
    else:
        # Fallback: try to extract text from unknown block types
        text = _extract_inline_text(content.get("content", []))
        return text + "\n" if text else None


def _render_heading(content: dict, heading_level: int | None) -> str:
    level = heading_level or content.get("attrs", {}).get("level", 2)
    text = _extract_inline_text(content.get("content", []))
    prefix = "#" * level
    return f"\n{prefix} {text}\n"


def _render_paragraph(content: dict) -> str:
    text = _extract_inline_text(content.get("content", []))
    return f"{text}\n"


def _render_code_block(content: dict) -> str:
    language = content.get("attrs", {}).get("language", "")
    code_text = _extract_plain_text(content.get("content", []))
    return f"\n```{language}\n{code_text}\n```\n"


def _render_bullet_list(content: dict, indent: int = 0) -> str:
    items = content.get("content", [])
    lines: list[str] = []
    prefix = "  " * indent

    for item in items:
        if not isinstance(item, dict):
            continue
        item_content = item.get("content", [])
        # Each listItem may contain paragraph(s) and nested lists
        first_para = True
        for child in item_content:
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                text = _extract_inline_text(child.get("content", []))
                if first_para:
                    lines.append(f"{prefix}- {text}")
                    first_para = False
                else:
                    lines.append(f"{prefix}  {text}")
            elif child_type == "bulletList":
                lines.append(_render_bullet_list(child, indent + 1))
            elif child_type == "orderedList":
                lines.append(_render_ordered_list(child, indent + 1))

    return "\n".join(lines) + "\n"


def _render_ordered_list(content: dict, indent: int = 0) -> str:
    items = content.get("content", [])
    lines: list[str] = []
    prefix = "  " * indent
    start = content.get("attrs", {}).get("start", 1)

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        item_content = item.get("content", [])
        num = start + idx
        first_para = True
        for child in item_content:
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                text = _extract_inline_text(child.get("content", []))
                if first_para:
                    lines.append(f"{prefix}{num}. {text}")
                    first_para = False
                else:
                    lines.append(f"{prefix}   {text}")
            elif child_type == "bulletList":
                lines.append(_render_bullet_list(child, indent + 1))
            elif child_type == "orderedList":
                lines.append(_render_ordered_list(child, indent + 1))

    return "\n".join(lines) + "\n"


def _render_task_list(content: dict) -> str:
    items = content.get("content", [])
    lines: list[str] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        checked = item.get("attrs", {}).get("checked", False)
        checkbox = "[x]" if checked else "[ ]"
        item_content = item.get("content", [])
        for child in item_content:
            if not isinstance(child, dict):
                continue
            if child.get("type") == "paragraph":
                text = _extract_inline_text(child.get("content", []))
                lines.append(f"- {checkbox} {text}")

    return "\n".join(lines) + "\n"


def _render_blockquote(content: dict) -> str:
    inner_content = content.get("content", [])
    lines: list[str] = []
    for child in inner_content:
        if not isinstance(child, dict):
            continue
        if child.get("type") == "paragraph":
            text = _extract_inline_text(child.get("content", []))
            lines.append(f"> {text}")
        else:
            text = _extract_inline_text(child.get("content", []))
            if text:
                lines.append(f"> {text}")
    return "\n".join(lines) + "\n"


def _render_image(content: dict) -> str:
    attrs = content.get("attrs", {})
    src = attrs.get("src", "")
    alt = attrs.get("alt", "")
    title = attrs.get("title", "")
    if title:
        return f'\n![{alt}]({src} "{title}")\n'
    return f"\n![{alt}]({src})\n"


def _render_table(content: dict) -> str:
    """Render a TipTap table to pipe-delimited Markdown table."""
    rows = content.get("content", [])
    if not rows:
        return ""

    table_rows: list[list[str]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("content", [])
        cell_texts: list[str] = []
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            # Extract text from cell content (may contain paragraphs)
            cell_content = cell.get("content", [])
            cell_parts: list[str] = []
            for child in cell_content:
                if isinstance(child, dict) and child.get("type") == "paragraph":
                    cell_parts.append(_extract_inline_text(child.get("content", [])))
                elif isinstance(child, dict):
                    cell_parts.append(_extract_inline_text(child.get("content", [])))
            cell_texts.append(" ".join(cell_parts).strip())
        table_rows.append(cell_texts)

    if not table_rows:
        return ""

    # Normalize column count
    max_cols = max(len(r) for r in table_rows)
    for row in table_rows:
        while len(row) < max_cols:
            row.append("")

    lines: list[str] = []

    # Header row
    header = table_rows[0]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")

    # Data rows
    for row in table_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n" + "\n".join(lines) + "\n"


# ── Inline text extraction ───────────────────────────────────────────


def _extract_inline_text(nodes: list) -> str:
    """Extract text with inline marks from a list of TipTap inline nodes."""
    parts: list[str] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type", "")

        if node_type == "text":
            text = node.get("text", "")
            marks = node.get("marks", [])
            parts.append(_apply_marks(text, marks))
        elif node_type == "hardBreak":
            parts.append("  \n")
        elif node_type == "image":
            attrs = node.get("attrs", {})
            src = attrs.get("src", "")
            alt = attrs.get("alt", "")
            parts.append(f"![{alt}]({src})")
        elif node_type == "mention":
            attrs = node.get("attrs", {})
            label = attrs.get("label", attrs.get("id", ""))
            parts.append(f"@{label}")
        else:
            # Recurse into unknown inline nodes
            inner = _extract_inline_text(node.get("content", []))
            if inner:
                parts.append(inner)

    return "".join(parts)


def _extract_plain_text(nodes: list) -> str:
    """Extract plain text without marks (for code blocks)."""
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


def _apply_marks(text: str, marks: list) -> str:
    """Wrap text with Markdown syntax for each TipTap mark."""
    if not marks:
        return text

    for mark in marks:
        mark_type = mark.get("type", "")
        attrs = mark.get("attrs", {})

        if mark_type == "bold":
            text = f"**{text}**"
        elif mark_type == "italic":
            text = f"*{text}*"
        elif mark_type == "code":
            text = f"`{text}`"
        elif mark_type == "strike":
            text = f"~~{text}~~"
        elif mark_type == "underline":
            text = f"<u>{text}</u>"
        elif mark_type == "link":
            href = attrs.get("href", "")
            text = f"[{text}]({href})"
        elif mark_type == "highlight":
            text = f"=={text}=="

    return text
