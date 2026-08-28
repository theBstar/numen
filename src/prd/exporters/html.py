"""HTML exporter - convert TipTap JSON blocks to HTML string.

Produces a complete HTML document with optional inline CSS for
professional styling (Numen branding). Includes table of contents
generated from headings and a metadata header section.
"""

from __future__ import annotations

import html as html_mod


def export_to_html(
    title: str,
    blocks: list[dict],
    metadata: dict | None = None,
    styled: bool = True,
) -> str:
    """Convert TipTap JSON blocks to an HTML string.

    Args:
        title: Document title.
        blocks: List of TipTap block dicts (each with block_type, content, heading_level).
        metadata: Optional dict with keys like status, owner, tags, target_date, description.
        styled: If True, include inline CSS for professional styling.

    Returns:
        Complete HTML document as a string.
    """
    body_parts: list[str] = []

    # Metadata header
    if metadata:
        body_parts.append(_build_metadata_header(title, metadata))
    else:
        body_parts.append(f"<h1>{_esc(title)}</h1>")

    # Table of contents
    toc = _build_toc(blocks)
    if toc:
        body_parts.append(toc)

    # Content blocks
    for block in blocks:
        content = block.get("content", {})
        block_type = block.get("block_type", "paragraph")
        heading_level = block.get("heading_level")
        slug = block.get("slug", "")

        rendered = _render_block(block_type, content, heading_level, slug)
        if rendered:
            body_parts.append(rendered)

    body_html = "\n".join(body_parts)

    if styled:
        return _wrap_styled_document(title, body_html)
    return _wrap_plain_document(title, body_html)


# ── Document wrappers ────────────────────────────────────────────────


def _wrap_styled_document(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
<style>
{_get_styles()}
</style>
</head>
<body>
<div class="document">
{body}
</div>
</body>
</html>"""


def _wrap_plain_document(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_esc(title)}</title>
</head>
<body>
{body}
</body>
</html>"""


def _get_styles() -> str:
    return """
:root {
  --numen-primary: #4F46E5;
  --numen-primary-light: #EEF2FF;
  --numen-text: #1F2937;
  --numen-text-secondary: #6B7280;
  --numen-border: #E5E7EB;
  --numen-bg: #FFFFFF;
  --numen-code-bg: #F3F4F6;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 16px;
  line-height: 1.7;
  color: var(--numen-text);
  background: var(--numen-bg);
}

.document {
  max-width: 800px;
  margin: 0 auto;
  padding: 48px 32px;
}

h1, h2, h3, h4, h5, h6 {
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  font-weight: 600;
  line-height: 1.3;
}

h1 { font-size: 2em; border-bottom: 2px solid var(--numen-primary); padding-bottom: 0.3em; }
h2 { font-size: 1.5em; border-bottom: 1px solid var(--numen-border); padding-bottom: 0.2em; }
h3 { font-size: 1.25em; }
h4 { font-size: 1.1em; }

p { margin-bottom: 1em; }

a { color: var(--numen-primary); text-decoration: none; }
a:hover { text-decoration: underline; }

code {
  background: var(--numen-code-bg);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
}

pre {
  background: #1E293B;
  color: #E2E8F0;
  padding: 16px 20px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 1em 0;
  font-size: 0.9em;
  line-height: 1.5;
}

pre code {
  background: none;
  padding: 0;
  color: inherit;
}

blockquote {
  border-left: 4px solid var(--numen-primary);
  padding: 12px 20px;
  margin: 1em 0;
  background: var(--numen-primary-light);
  border-radius: 0 8px 8px 0;
}

blockquote p { margin-bottom: 0.5em; }
blockquote p:last-child { margin-bottom: 0; }

ul, ol { margin: 0.5em 0; padding-left: 2em; }
li { margin-bottom: 0.3em; }

ul.task-list { list-style: none; padding-left: 0; }
ul.task-list li { position: relative; padding-left: 1.5em; }
ul.task-list li input[type="checkbox"] {
  position: absolute;
  left: 0;
  top: 0.35em;
}

hr {
  border: none;
  border-top: 2px solid var(--numen-border);
  margin: 2em 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  margin: 1em 0;
  font-size: 0.95em;
}

th, td {
  border: 1px solid var(--numen-border);
  padding: 10px 14px;
  text-align: left;
}

th {
  background: var(--numen-primary-light);
  font-weight: 600;
}

tr:nth-child(even) { background: #F9FAFB; }

img {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 1em 0;
}

.metadata-header {
  background: var(--numen-primary-light);
  border: 1px solid var(--numen-border);
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 32px;
}

.metadata-header h1 {
  margin-top: 0;
  border-bottom: none;
  padding-bottom: 0;
}

.metadata-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-top: 16px;
  font-size: 0.9em;
}

.metadata-item {
  display: flex;
  flex-direction: column;
}

.metadata-label {
  font-weight: 600;
  color: var(--numen-text-secondary);
  font-size: 0.85em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metadata-value {
  color: var(--numen-text);
}

.toc {
  background: #F9FAFB;
  border: 1px solid var(--numen-border);
  border-radius: 8px;
  padding: 20px 24px;
  margin-bottom: 32px;
}

.toc-title {
  font-weight: 600;
  font-size: 0.9em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--numen-text-secondary);
  margin-bottom: 12px;
}

.toc ul { list-style: none; padding-left: 0; }
.toc ul ul { padding-left: 1.5em; }
.toc li { margin-bottom: 6px; }
.toc a { font-size: 0.95em; }

.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: 600;
  text-transform: uppercase;
}

.badge-status {
  background: var(--numen-primary);
  color: white;
}

.tag {
  display: inline-block;
  background: var(--numen-code-bg);
  color: var(--numen-text-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 0.85em;
  margin-right: 4px;
}

u { text-decoration: underline; }
s { text-decoration: line-through; }
mark { background: #FEF08A; padding: 1px 4px; border-radius: 2px; }
"""


# ── Metadata header ──────────────────────────────────────────────────


def _build_metadata_header(title: str, metadata: dict) -> str:
    lines = ['<div class="metadata-header">']
    lines.append(f"  <h1>{_esc(title)}</h1>")

    if metadata.get("description"):
        lines.append(f"  <p>{_esc(metadata['description'])}</p>")

    lines.append('  <div class="metadata-grid">')

    if metadata.get("status"):
        lines.append('    <div class="metadata-item">')
        lines.append('      <span class="metadata-label">Status</span>')
        lines.append(
            f'      <span class="metadata-value"><span class="badge badge-status">'
            f"{_esc(metadata['status'])}</span></span>"
        )
        lines.append("    </div>")

    if metadata.get("owner"):
        lines.append('    <div class="metadata-item">')
        lines.append('      <span class="metadata-label">Owner</span>')
        lines.append(f'      <span class="metadata-value">{_esc(metadata["owner"])}</span>')
        lines.append("    </div>")

    if metadata.get("priority"):
        lines.append('    <div class="metadata-item">')
        lines.append('      <span class="metadata-label">Priority</span>')
        lines.append(f'      <span class="metadata-value">{_esc(metadata["priority"])}</span>')
        lines.append("    </div>")

    if metadata.get("target_date"):
        lines.append('    <div class="metadata-item">')
        lines.append('      <span class="metadata-label">Target Date</span>')
        lines.append(
            f'      <span class="metadata-value">{_esc(str(metadata["target_date"]))}</span>'
        )
        lines.append("    </div>")

    lines.append("  </div>")

    if metadata.get("tags"):
        lines.append('  <div style="margin-top: 12px;">')
        for tag in metadata["tags"]:
            lines.append(f'    <span class="tag">{_esc(tag)}</span>')
        lines.append("  </div>")

    lines.append("</div>")
    return "\n".join(lines)


# ── Table of contents ────────────────────────────────────────────────


def _build_toc(blocks: list[dict]) -> str:
    """Build an HTML table of contents from heading blocks."""
    headings: list[tuple[int, str, str]] = []
    for block in blocks:
        if block.get("block_type") != "heading":
            continue
        content = block.get("content", {})
        level = block.get("heading_level") or content.get("attrs", {}).get("level", 2)
        slug = block.get("slug", "")
        text = _extract_plain_text(content.get("content", []))
        if text:
            headings.append((level, text, slug))

    if not headings:
        return ""

    lines = ['<nav class="toc">']
    lines.append('  <div class="toc-title">Table of Contents</div>')
    lines.append("  <ul>")

    min_level = min(h[0] for h in headings)
    prev_level = min_level

    for level, text, slug in headings:
        # Open nested lists as needed
        while level > prev_level:
            lines.append("    <ul>")
            prev_level += 1
        # Close nested lists as needed
        while level < prev_level:
            lines.append("    </ul>")
            prev_level -= 1

        anchor = f"#{slug}" if slug else ""
        lines.append(f'    <li><a href="{anchor}">{_esc(text)}</a></li>')
        prev_level = level

    # Close any remaining open lists
    while prev_level > min_level:
        lines.append("    </ul>")
        prev_level -= 1

    lines.append("  </ul>")
    lines.append("</nav>")
    return "\n".join(lines)


# ── Block rendering ──────────────────────────────────────────────────


def _render_block(
    block_type: str,
    content: dict,
    heading_level: int | None = None,
    slug: str = "",
) -> str | None:
    """Render a single TipTap block to HTML."""
    if block_type == "heading":
        return _render_heading(content, heading_level, slug)
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
        return "<hr>"
    elif block_type == "table":
        return _render_table(content)
    else:
        text = _extract_inline_html(content.get("content", []))
        return f"<p>{text}</p>" if text else None


def _render_heading(content: dict, heading_level: int | None, slug: str) -> str:
    level = heading_level or content.get("attrs", {}).get("level", 2)
    text = _extract_inline_html(content.get("content", []))
    id_attr = f' id="{_esc(slug)}"' if slug else ""
    return f"<h{level}{id_attr}>{text}</h{level}>"


def _render_paragraph(content: dict) -> str:
    text = _extract_inline_html(content.get("content", []))
    return f"<p>{text}</p>"


def _render_code_block(content: dict) -> str:
    language = content.get("attrs", {}).get("language", "")
    code_text = _extract_plain_text(content.get("content", []))
    lang_attr = f' class="language-{_esc(language)}"' if language else ""
    return f"<pre><code{lang_attr}>{_esc(code_text)}</code></pre>"


def _render_bullet_list(content: dict) -> str:
    items = content.get("content", [])
    lines = ["<ul>"]
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append("  <li>")
        for child in item.get("content", []):
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                text = _extract_inline_html(child.get("content", []))
                lines.append(f"    {text}")
            elif child_type == "bulletList":
                lines.append(f"    {_render_bullet_list(child)}")
            elif child_type == "orderedList":
                lines.append(f"    {_render_ordered_list(child)}")
        lines.append("  </li>")
    lines.append("</ul>")
    return "\n".join(lines)


def _render_ordered_list(content: dict) -> str:
    items = content.get("content", [])
    start = content.get("attrs", {}).get("start", 1)
    start_attr = f' start="{start}"' if start != 1 else ""
    lines = [f"<ol{start_attr}>"]
    for item in items:
        if not isinstance(item, dict):
            continue
        lines.append("  <li>")
        for child in item.get("content", []):
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                text = _extract_inline_html(child.get("content", []))
                lines.append(f"    {text}")
            elif child_type == "bulletList":
                lines.append(f"    {_render_bullet_list(child)}")
            elif child_type == "orderedList":
                lines.append(f"    {_render_ordered_list(child)}")
        lines.append("  </li>")
    lines.append("</ol>")
    return "\n".join(lines)


def _render_task_list(content: dict) -> str:
    items = content.get("content", [])
    lines = ['<ul class="task-list">']
    for item in items:
        if not isinstance(item, dict):
            continue
        checked = item.get("attrs", {}).get("checked", False)
        checked_attr = " checked" if checked else ""
        for child in item.get("content", []):
            if not isinstance(child, dict):
                continue
            if child.get("type") == "paragraph":
                text = _extract_inline_html(child.get("content", []))
                lines.append(f'  <li><input type="checkbox" disabled{checked_attr}> {text}</li>')
    lines.append("</ul>")
    return "\n".join(lines)


def _render_blockquote(content: dict) -> str:
    inner_content = content.get("content", [])
    lines = ["<blockquote>"]
    for child in inner_content:
        if not isinstance(child, dict):
            continue
        if child.get("type") == "paragraph":
            text = _extract_inline_html(child.get("content", []))
            lines.append(f"  <p>{text}</p>")
        else:
            text = _extract_inline_html(child.get("content", []))
            if text:
                lines.append(f"  <p>{text}</p>")
    lines.append("</blockquote>")
    return "\n".join(lines)


def _render_image(content: dict) -> str:
    attrs = content.get("attrs", {})
    src = _esc(attrs.get("src", ""))
    alt = _esc(attrs.get("alt", ""))
    title = _esc(attrs.get("title", ""))
    title_attr = f' title="{title}"' if title else ""
    return f'<img src="{src}" alt="{alt}"{title_attr}>'


def _render_table(content: dict) -> str:
    rows = content.get("content", [])
    if not rows:
        return ""

    lines = ["<table>"]
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        cells = row.get("content", [])
        is_header = idx == 0

        if is_header:
            lines.append("  <thead>")
        elif idx == 1:
            lines.append("  <tbody>")

        lines.append("    <tr>")
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            tag = "th" if is_header else "td"
            cell_content = cell.get("content", [])
            cell_parts: list[str] = []
            for child in cell_content:
                if isinstance(child, dict) and child.get("type") == "paragraph":
                    cell_parts.append(_extract_inline_html(child.get("content", [])))
                elif isinstance(child, dict):
                    cell_parts.append(_extract_inline_html(child.get("content", [])))
            cell_text = " ".join(cell_parts).strip()

            # Handle colspan/rowspan
            attrs_dict = cell.get("attrs", {})
            extra = ""
            if attrs_dict.get("colspan", 1) > 1:
                extra += f' colspan="{attrs_dict["colspan"]}"'
            if attrs_dict.get("rowspan", 1) > 1:
                extra += f' rowspan="{attrs_dict["rowspan"]}"'

            lines.append(f"      <{tag}{extra}>{cell_text}</{tag}>")
        lines.append("    </tr>")

        if is_header:
            lines.append("  </thead>")

    if len(rows) > 1:
        lines.append("  </tbody>")
    lines.append("</table>")
    return "\n".join(lines)


# ── Inline rendering ─────────────────────────────────────────────────


def _extract_inline_html(nodes: list) -> str:
    """Convert TipTap inline nodes to HTML with marks."""
    parts: list[str] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type", "")

        if node_type == "text":
            text = _esc(node.get("text", ""))
            marks = node.get("marks", [])
            parts.append(_apply_html_marks(text, marks))
        elif node_type == "hardBreak":
            parts.append("<br>")
        elif node_type == "image":
            attrs = node.get("attrs", {})
            src = _esc(attrs.get("src", ""))
            alt = _esc(attrs.get("alt", ""))
            parts.append(f'<img src="{src}" alt="{alt}">')
        elif node_type == "mention":
            attrs = node.get("attrs", {})
            label = _esc(attrs.get("label", attrs.get("id", "")))
            parts.append(f"<strong>@{label}</strong>")
        else:
            inner = _extract_inline_html(node.get("content", []))
            if inner:
                parts.append(inner)

    return "".join(parts)


def _extract_plain_text(nodes: list) -> str:
    """Extract plain text without marks."""
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


def _apply_html_marks(text: str, marks: list) -> str:
    """Wrap text with HTML tags for each TipTap mark."""
    if not marks:
        return text

    for mark in marks:
        mark_type = mark.get("type", "")
        attrs = mark.get("attrs", {})

        if mark_type == "bold":
            text = f"<strong>{text}</strong>"
        elif mark_type == "italic":
            text = f"<em>{text}</em>"
        elif mark_type == "code":
            text = f"<code>{text}</code>"
        elif mark_type == "strike":
            text = f"<s>{text}</s>"
        elif mark_type == "underline":
            text = f"<u>{text}</u>"
        elif mark_type == "link":
            href = _esc(attrs.get("href", ""))
            target = attrs.get("target", "")
            target_attr = f' target="{_esc(target)}"' if target else ""
            text = f'<a href="{href}"{target_attr}>{text}</a>'
        elif mark_type == "highlight":
            text = f"<mark>{text}</mark>"

    return text


def _esc(text: str) -> str:
    """HTML-escape a string."""
    return html_mod.escape(text, quote=True)
