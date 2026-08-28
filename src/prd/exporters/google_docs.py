"""Google Docs exporter - create a Google Doc from TipTap JSON blocks.

Creates a Google Doc via the Google Docs API, then populates content
using batchUpdate requests. Optionally moves the doc to a specific
Drive folder. Uses httpx for async HTTP calls.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DOCS_API_BASE = "https://docs.googleapis.com/v1"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


async def export_to_google_docs(
    access_token: str,
    blocks: list[dict],
    title: str,
    folder_id: str | None = None,
) -> dict:
    """Create a Google Doc from TipTap JSON blocks.

    Args:
        access_token: Google OAuth2 access token with Docs and Drive scopes.
        blocks: List of TipTap block dicts.
        title: Document title.
        folder_id: Optional Google Drive folder ID to move the document into.

    Returns:
        {"url": str, "external_id": str} with the document URL and ID.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Create the document
        create_response = await client.post(
            f"{DOCS_API_BASE}/documents",
            json={"title": title},
            headers=headers,
        )

        if create_response.status_code not in (200, 201):
            logger.error(
                "Google Docs create error %d: %s",
                create_response.status_code,
                create_response.text,
            )
            raise RuntimeError(
                f"Google Docs API error {create_response.status_code}: {create_response.text}"
            )

        doc = create_response.json()
        doc_id = doc["documentId"]
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        # Step 2: Build batchUpdate requests to insert content
        requests = _build_batch_update_requests(blocks)

        if requests:
            batch_response = await client.post(
                f"{DOCS_API_BASE}/documents/{doc_id}:batchUpdate",
                json={"requests": requests},
                headers=headers,
            )

            if batch_response.status_code not in (200, 201):
                logger.error(
                    "Google Docs batchUpdate error %d: %s",
                    batch_response.status_code,
                    batch_response.text,
                )
                # Document was created but content insertion failed - log but continue
                logger.warning("Document %s created but content insertion failed", doc_id)

        # Step 3: Move to folder if specified
        if folder_id:
            await _move_to_folder(client, headers, doc_id, folder_id)

        return {
            "url": doc_url,
            "external_id": doc_id,
        }


async def _move_to_folder(
    client: httpx.AsyncClient,
    headers: dict,
    doc_id: str,
    folder_id: str,
) -> None:
    """Move a Google Doc to a specific Drive folder."""
    try:
        # Get current parents
        get_response = await client.get(
            f"{DRIVE_API_BASE}/files/{doc_id}",
            params={"fields": "parents"},
            headers=headers,
        )

        if get_response.status_code == 200:
            current_parents = get_response.json().get("parents", [])
            remove_parents = ",".join(current_parents)

            await client.patch(
                f"{DRIVE_API_BASE}/files/{doc_id}",
                params={
                    "addParents": folder_id,
                    "removeParents": remove_parents,
                },
                headers=headers,
            )
    except Exception:
        logger.warning("Failed to move document %s to folder %s", doc_id, folder_id)


# ── batchUpdate request building ─────────────────────────────────────


def _build_batch_update_requests(blocks: list[dict]) -> list[dict]:
    """Build Google Docs batchUpdate requests from TipTap blocks.

    Google Docs API inserts content at a specific index. We insert
    content in reverse order at index 1 (right after the implicit
    empty paragraph) so that earlier blocks end up at the top.
    """
    # First, build the content in order, then reverse for insertion
    segments: list[dict] = []

    for block in blocks:
        block_type = block.get("block_type", "paragraph")
        content = block.get("content", {})
        heading_level = block.get("heading_level")

        block_segments = _convert_block_to_segments(block_type, content, heading_level)
        segments.extend(block_segments)

    if not segments:
        return []

    # Build requests by inserting in reverse at index 1
    requests: list[dict] = []
    current_index = 1

    for segment in segments:
        seg_type = segment.get("type")

        if seg_type == "text":
            text = segment["text"]
            requests.append(
                {
                    "insertText": {
                        "location": {"index": current_index},
                        "text": text,
                    }
                }
            )

            # Apply paragraph style if this ends with a newline and has a named style
            style = segment.get("style")
            if style and text.endswith("\n"):
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": current_index,
                                "endIndex": current_index + len(text) - 1,
                            },
                            "paragraphStyle": {
                                "namedStyleType": style,
                            },
                            "fields": "namedStyleType",
                        }
                    }
                )

            # Apply text style (bold, italic, etc.)
            text_style = segment.get("text_style")
            if text_style:
                fields = list(text_style.keys())
                requests.append(
                    {
                        "updateTextStyle": {
                            "range": {
                                "startIndex": current_index,
                                "endIndex": current_index + len(text),
                            },
                            "textStyle": text_style,
                            "fields": ",".join(fields),
                        }
                    }
                )

            current_index += len(text)

        elif seg_type == "image":
            uri = segment["uri"]
            requests.append(
                {
                    "insertInlineImage": {
                        "location": {"index": current_index},
                        "uri": uri,
                        "objectSize": {
                            "width": {"magnitude": 400, "unit": "PT"},
                        },
                    }
                }
            )
            current_index += 1  # Inline image takes 1 index
            # Add newline after image
            requests.append(
                {
                    "insertText": {
                        "location": {"index": current_index},
                        "text": "\n",
                    }
                }
            )
            current_index += 1

    return requests


def _convert_block_to_segments(
    block_type: str,
    content: dict,
    heading_level: int | None = None,
) -> list[dict]:
    """Convert a TipTap block to a list of insert segments."""
    if block_type == "heading":
        return _segments_heading(content, heading_level)
    elif block_type == "paragraph":
        return _segments_paragraph(content)
    elif block_type == "codeBlock":
        return _segments_code_block(content)
    elif block_type == "bulletList":
        return _segments_bullet_list(content)
    elif block_type == "orderedList":
        return _segments_ordered_list(content)
    elif block_type == "taskList":
        return _segments_task_list(content)
    elif block_type == "blockquote":
        return _segments_blockquote(content)
    elif block_type == "image":
        return _segments_image(content)
    elif block_type == "horizontalRule":
        return [{"type": "text", "text": "\n---\n", "style": "NORMAL_TEXT"}]
    elif block_type == "table":
        return _segments_table(content)
    else:
        segments = _inline_to_segments(content.get("content", []))
        segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})
        return segments


def _segments_heading(content: dict, heading_level: int | None) -> list[dict]:
    level = heading_level or content.get("attrs", {}).get("level", 2)
    level = max(1, min(6, level))
    style = f"HEADING_{level}"

    segments = _inline_to_segments(content.get("content", []))
    segments.append({"type": "text", "text": "\n", "style": style})
    return segments


def _segments_paragraph(content: dict) -> list[dict]:
    segments = _inline_to_segments(content.get("content", []))
    segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})
    return segments


def _segments_code_block(content: dict) -> list[dict]:
    code_text = _extract_plain_text(content.get("content", []))
    return [
        {
            "type": "text",
            "text": code_text + "\n",
            "style": "NORMAL_TEXT",
            "text_style": {
                "weightedFontFamily": {
                    "fontFamily": "Courier New",
                    "weight": 400,
                },
                "fontSize": {"magnitude": 10, "unit": "PT"},
            },
        }
    ]


def _segments_bullet_list(content: dict, indent: int = 0) -> list[dict]:
    items = content.get("content", [])
    segments: list[dict] = []
    bullet_chars = ["- ", "  - ", "    - "]
    prefix = bullet_chars[min(indent, len(bullet_chars) - 1)]

    for item in items:
        if not isinstance(item, dict):
            continue
        for child in item.get("content", []):
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                segments.append({"type": "text", "text": prefix})
                segments.extend(_inline_to_segments(child.get("content", [])))
                segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})
            elif child_type == "bulletList":
                segments.extend(_segments_bullet_list(child, indent + 1))
            elif child_type == "orderedList":
                segments.extend(_segments_ordered_list(child, indent + 1))

    return segments


def _segments_ordered_list(content: dict, indent: int = 0) -> list[dict]:
    items = content.get("content", [])
    segments: list[dict] = []
    start = content.get("attrs", {}).get("start", 1)
    prefix_indent = "  " * indent

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        num = start + idx
        for child in item.get("content", []):
            if not isinstance(child, dict):
                continue
            child_type = child.get("type", "")
            if child_type == "paragraph":
                segments.append({"type": "text", "text": f"{prefix_indent}{num}. "})
                segments.extend(_inline_to_segments(child.get("content", [])))
                segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})
            elif child_type == "bulletList":
                segments.extend(_segments_bullet_list(child, indent + 1))
            elif child_type == "orderedList":
                segments.extend(_segments_ordered_list(child, indent + 1))

    return segments


def _segments_task_list(content: dict) -> list[dict]:
    items = content.get("content", [])
    segments: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        checked = item.get("attrs", {}).get("checked", False)
        checkbox = "[x] " if checked else "[ ] "

        for child in item.get("content", []):
            if isinstance(child, dict) and child.get("type") == "paragraph":
                segments.append({"type": "text", "text": checkbox})
                segments.extend(_inline_to_segments(child.get("content", [])))
                segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})

    return segments


def _segments_blockquote(content: dict) -> list[dict]:
    inner = content.get("content", [])
    segments: list[dict] = []

    for child in inner:
        if isinstance(child, dict) and child.get("type") == "paragraph":
            segments.append({"type": "text", "text": "> "})
            segments.extend(_inline_to_segments(child.get("content", [])))
            segments.append({"type": "text", "text": "\n", "style": "NORMAL_TEXT"})

    return segments


def _segments_image(content: dict) -> list[dict]:
    attrs = content.get("attrs", {})
    src = attrs.get("src", "")
    if src:
        return [{"type": "image", "uri": src}]
    return []


def _segments_table(content: dict) -> list[dict]:
    """Convert table to plain text representation for Google Docs.

    Google Docs API does support tables via insertTable, but the
    complexity of managing cell indices makes plain text more reliable
    for an initial implementation.
    """
    rows = content.get("content", [])
    segments: list[dict] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("content", [])
        cell_texts: list[str] = []
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            cell_content = cell.get("content", [])
            parts: list[str] = []
            for child in cell_content:
                if isinstance(child, dict) and child.get("type") == "paragraph":
                    parts.append(_extract_plain_text(child.get("content", [])))
            cell_texts.append(" ".join(parts).strip())

        row_text = " | ".join(cell_texts)
        segments.append({"type": "text", "text": row_text + "\n", "style": "NORMAL_TEXT"})

    return segments


# ── Inline conversion ────────────────────────────────────────────────


def _inline_to_segments(nodes: list) -> list[dict]:
    """Convert TipTap inline nodes to Google Docs insert segments."""
    segments: list[dict] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type", "")

        if node_type == "text":
            text = node.get("text", "")
            marks = node.get("marks", [])
            text_style = _marks_to_gdocs_style(marks)
            link = _extract_link_from_marks(marks)

            seg: dict[str, Any] = {"type": "text", "text": text}
            if text_style:
                seg["text_style"] = text_style
            if link:
                seg.setdefault("text_style", {})["link"] = {"url": link}
            segments.append(seg)

        elif node_type == "hardBreak":
            segments.append({"type": "text", "text": "\n"})

        elif node_type == "image":
            attrs = node.get("attrs", {})
            src = attrs.get("src", "")
            if src:
                segments.append({"type": "image", "uri": src})

        elif node_type == "mention":
            attrs = node.get("attrs", {})
            label = attrs.get("label", attrs.get("id", ""))
            segments.append(
                {
                    "type": "text",
                    "text": f"@{label}",
                    "text_style": {"bold": True},
                }
            )

    return segments


def _marks_to_gdocs_style(marks: list) -> dict:
    """Convert TipTap marks to Google Docs text style dict."""
    style: dict[str, Any] = {}

    for mark in marks:
        mark_type = mark.get("type", "")
        if mark_type == "bold":
            style["bold"] = True
        elif mark_type == "italic":
            style["italic"] = True
        elif mark_type == "code":
            style["weightedFontFamily"] = {
                "fontFamily": "Courier New",
                "weight": 400,
            }
        elif mark_type == "strike":
            style["strikethrough"] = True
        elif mark_type == "underline":
            style["underline"] = True

    return style


def _extract_link_from_marks(marks: list) -> str | None:
    """Extract link href from TipTap marks."""
    for mark in marks:
        if mark.get("type") == "link":
            return mark.get("attrs", {}).get("href")
    return None


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
