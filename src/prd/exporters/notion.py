"""Notion exporter - create a Notion page from TipTap JSON blocks.

Converts TipTap block structure to Notion block API format and creates
a page via the Notion API. Uses httpx for async HTTP calls.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

NOTION_API_VERSION = "2022-06-28"
NOTION_API_BASE = "https://api.notion.com/v1"


async def export_to_notion(
    access_token: str,
    blocks: list[dict],
    title: str,
    parent_page_id: str | None = None,
) -> dict:
    """Create a Notion page from TipTap JSON blocks.

    Args:
        access_token: Notion integration token or OAuth token.
        blocks: List of TipTap block dicts.
        title: Page title.
        parent_page_id: Optional parent page ID. If None, creates in workspace root.

    Returns:
        {"url": str, "external_id": str} with the created page URL and ID.
    """
    notion_blocks = _convert_blocks_to_notion(blocks)

    # Build the page creation payload
    page_data: dict[str, Any] = {
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": notion_blocks,
    }

    if parent_page_id:
        page_data["parent"] = {"type": "page_id", "page_id": parent_page_id}
    else:
        # Default: create as a page in the workspace
        page_data["parent"] = {"type": "workspace", "workspace": True}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Notion-Version": NOTION_API_VERSION,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{NOTION_API_BASE}/pages",
            json=page_data,
            headers=headers,
        )

        if response.status_code not in (200, 201):
            logger.error("Notion API error %d: %s", response.status_code, response.text)
            raise RuntimeError(f"Notion API error {response.status_code}: {response.text}")

        result = response.json()
        return {
            "url": result.get("url", ""),
            "external_id": result.get("id", ""),
        }


# ── Block conversion ─────────────────────────────────────────────────


def _convert_blocks_to_notion(blocks: list[dict]) -> list[dict]:
    """Convert a list of TipTap blocks to Notion block objects."""
    notion_blocks: list[dict] = []

    for block in blocks:
        block_type = block.get("block_type", "paragraph")
        content = block.get("content", {})
        heading_level = block.get("heading_level")

        converted = _convert_block(block_type, content, heading_level)
        if converted:
            if isinstance(converted, list):
                notion_blocks.extend(converted)
            else:
                notion_blocks.append(converted)

    return notion_blocks


def _convert_block(
    block_type: str,
    content: dict,
    heading_level: int | None = None,
) -> dict | list[dict] | None:
    """Convert a single TipTap block to a Notion block object."""
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
        return {"type": "divider", "divider": {}}
    elif block_type == "table":
        return _convert_table(content)
    else:
        # Fallback: paragraph
        rich_text = _tiptap_inline_to_notion_rich_text(content.get("content", []))
        if rich_text:
            return {"type": "paragraph", "paragraph": {"rich_text": rich_text}}
        return None


def _convert_heading(content: dict, heading_level: int | None) -> dict:
    level = heading_level or content.get("attrs", {}).get("level", 2)
    rich_text = _tiptap_inline_to_notion_rich_text(content.get("content", []))

    # Notion supports heading_1, heading_2, heading_3 only
    if level >= 3:
        notion_type = "heading_3"
    elif level == 2:
        notion_type = "heading_2"
    else:
        notion_type = "heading_1"

    return {"type": notion_type, notion_type: {"rich_text": rich_text}}


def _convert_paragraph(content: dict) -> dict:
    rich_text = _tiptap_inline_to_notion_rich_text(content.get("content", []))
    return {"type": "paragraph", "paragraph": {"rich_text": rich_text}}


def _convert_code_block(content: dict) -> dict:
    language = content.get("attrs", {}).get("language", "plain text") or "plain text"
    code_text = _extract_plain_text(content.get("content", []))

    return {
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": code_text}}],
            "language": _normalize_notion_language(language),
        },
    }


def _convert_bullet_list(content: dict) -> list[dict]:
    items = content.get("content", [])
    notion_items: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        rich_text, children = _extract_list_item_content(item)
        block: dict[str, Any] = {
            "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": rich_text},
        }
        if children:
            block["bulleted_list_item"]["children"] = children
        notion_items.append(block)

    return notion_items


def _convert_ordered_list(content: dict) -> list[dict]:
    items = content.get("content", [])
    notion_items: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        rich_text, children = _extract_list_item_content(item)
        block: dict[str, Any] = {
            "type": "numbered_list_item",
            "numbered_list_item": {"rich_text": rich_text},
        }
        if children:
            block["numbered_list_item"]["children"] = children
        notion_items.append(block)

    return notion_items


def _convert_task_list(content: dict) -> list[dict]:
    items = content.get("content", [])
    notion_items: list[dict] = []

    for item in items:
        if not isinstance(item, dict):
            continue
        checked = item.get("attrs", {}).get("checked", False)
        rich_text = []
        for child in item.get("content", []):
            if isinstance(child, dict) and child.get("type") == "paragraph":
                rich_text = _tiptap_inline_to_notion_rich_text(child.get("content", []))
                break

        notion_items.append(
            {
                "type": "to_do",
                "to_do": {
                    "rich_text": rich_text,
                    "checked": checked,
                },
            }
        )

    return notion_items


def _convert_blockquote(content: dict) -> dict:
    inner = content.get("content", [])
    rich_text_parts: list[dict] = []
    for child in inner:
        if isinstance(child, dict) and child.get("type") == "paragraph":
            parts = _tiptap_inline_to_notion_rich_text(child.get("content", []))
            rich_text_parts.extend(parts)
            # Add newline between paragraphs in blockquote
            rich_text_parts.append({"type": "text", "text": {"content": "\n"}})

    # Remove trailing newline
    if rich_text_parts and rich_text_parts[-1].get("text", {}).get("content") == "\n":
        rich_text_parts.pop()

    return {"type": "quote", "quote": {"rich_text": rich_text_parts}}


def _convert_image(content: dict) -> dict:
    attrs = content.get("attrs", {})
    src = attrs.get("src", "")

    return {
        "type": "image",
        "image": {
            "type": "external",
            "external": {"url": src},
        },
    }


def _convert_table(content: dict) -> dict:
    rows = content.get("content", [])
    if not rows:
        return {"type": "paragraph", "paragraph": {"rich_text": []}}

    table_rows: list[dict] = []
    table_width = 0

    for row in rows:
        if not isinstance(row, dict):
            continue
        cells = row.get("content", [])
        row_cells: list[list[dict]] = []
        for cell in cells:
            if not isinstance(cell, dict):
                continue
            cell_content = cell.get("content", [])
            rich_text: list[dict] = []
            for child in cell_content:
                if isinstance(child, dict) and child.get("type") == "paragraph":
                    rich_text.extend(_tiptap_inline_to_notion_rich_text(child.get("content", [])))
            row_cells.append(rich_text)

        if not table_width:
            table_width = len(row_cells)

        table_rows.append(
            {
                "type": "table_row",
                "table_row": {"cells": row_cells},
            }
        )

    return {
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": True,
            "has_row_header": False,
            "children": table_rows,
        },
    }


# ── List item helpers ────────────────────────────────────────────────


def _extract_list_item_content(item: dict) -> tuple[list[dict], list[dict]]:
    """Extract rich_text and nested children from a TipTap list item.

    Returns:
        Tuple of (rich_text for the item, list of child Notion blocks).
    """
    rich_text: list[dict] = []
    children: list[dict] = []

    for child in item.get("content", []):
        if not isinstance(child, dict):
            continue
        child_type = child.get("type", "")
        if child_type == "paragraph":
            rich_text = _tiptap_inline_to_notion_rich_text(child.get("content", []))
        elif child_type == "bulletList":
            items = child.get("content", [])
            for sub_item in items:
                if not isinstance(sub_item, dict):
                    continue
                sub_rt, sub_children = _extract_list_item_content(sub_item)
                block: dict[str, Any] = {
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": sub_rt},
                }
                if sub_children:
                    block["bulleted_list_item"]["children"] = sub_children
                children.append(block)
        elif child_type == "orderedList":
            items = child.get("content", [])
            for sub_item in items:
                if not isinstance(sub_item, dict):
                    continue
                sub_rt, sub_children = _extract_list_item_content(sub_item)
                block = {
                    "type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": sub_rt},
                }
                if sub_children:
                    block["numbered_list_item"]["children"] = sub_children
                children.append(block)

    return rich_text, children


# ── Rich text conversion ─────────────────────────────────────────────


def _tiptap_inline_to_notion_rich_text(nodes: list) -> list[dict]:
    """Convert TipTap inline nodes to Notion rich text array."""
    rich_text: list[dict] = []

    for node in nodes:
        if not isinstance(node, dict):
            continue

        node_type = node.get("type", "")

        if node_type == "text":
            text_content = node.get("text", "")
            marks = node.get("marks", [])
            annotations = _marks_to_notion_annotations(marks)
            link = _extract_link_from_marks(marks)

            rt: dict[str, Any] = {
                "type": "text",
                "text": {"content": text_content},
                "annotations": annotations,
            }
            if link:
                rt["text"]["link"] = {"url": link}

            rich_text.append(rt)

        elif node_type == "hardBreak":
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": "\n"},
                }
            )

        elif node_type == "mention":
            attrs = node.get("attrs", {})
            label = attrs.get("label", attrs.get("id", ""))
            rich_text.append(
                {
                    "type": "text",
                    "text": {"content": f"@{label}"},
                    "annotations": {"bold": True},
                }
            )

    return rich_text


def _marks_to_notion_annotations(marks: list) -> dict:
    """Convert TipTap marks to Notion annotations dict."""
    annotations: dict[str, Any] = {
        "bold": False,
        "italic": False,
        "strikethrough": False,
        "underline": False,
        "code": False,
    }

    for mark in marks:
        mark_type = mark.get("type", "")
        if mark_type == "bold":
            annotations["bold"] = True
        elif mark_type == "italic":
            annotations["italic"] = True
        elif mark_type == "strike":
            annotations["strikethrough"] = True
        elif mark_type == "underline":
            annotations["underline"] = True
        elif mark_type == "code":
            annotations["code"] = True

    return annotations


def _extract_link_from_marks(marks: list) -> str | None:
    """Extract link href from TipTap marks if present."""
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


# ── Language normalization ───────────────────────────────────────────


_NOTION_LANGUAGES = {
    "abap",
    "arduino",
    "bash",
    "basic",
    "c",
    "clojure",
    "coffeescript",
    "cpp",
    "csharp",
    "css",
    "dart",
    "diff",
    "docker",
    "elixir",
    "elm",
    "erlang",
    "flow",
    "fortran",
    "fsharp",
    "gherkin",
    "glsl",
    "go",
    "graphql",
    "groovy",
    "haskell",
    "html",
    "java",
    "javascript",
    "json",
    "julia",
    "kotlin",
    "latex",
    "less",
    "lisp",
    "livescript",
    "lua",
    "makefile",
    "markdown",
    "markup",
    "matlab",
    "mermaid",
    "nix",
    "objective-c",
    "ocaml",
    "pascal",
    "perl",
    "php",
    "plain text",
    "powershell",
    "prolog",
    "protobuf",
    "python",
    "r",
    "reason",
    "ruby",
    "rust",
    "sass",
    "scala",
    "scheme",
    "scss",
    "shell",
    "sql",
    "swift",
    "typescript",
    "vb.net",
    "verilog",
    "vhdl",
    "visual basic",
    "webassembly",
    "xml",
    "yaml",
    "java/c/c++/c#",
}

_LANGUAGE_ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "rb": "ruby",
    "sh": "shell",
    "yml": "yaml",
    "cs": "csharp",
    "c++": "cpp",
    "c#": "csharp",
    "objective_c": "objective-c",
    "objc": "objective-c",
    "plaintext": "plain text",
    "text": "plain text",
    "": "plain text",
}


def _normalize_notion_language(language: str) -> str:
    """Normalize a language string to a Notion-supported language."""
    lang = language.lower().strip()
    if lang in _NOTION_LANGUAGES:
        return lang
    if lang in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[lang]
    return "plain text"
