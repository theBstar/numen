"""Import PDF documents as PRDs by extracting text, tables, and images.

Uses pdfplumber for layout-aware text extraction with font size-based
heading detection and table parsing. Processes page-by-page to handle
large documents (25+ pages) without excessive memory.
"""

from __future__ import annotations

import io
import logging
import re
import statistics
from collections import defaultdict

import pdfplumber

from src.prd.importer import ImportedBlock, ImportedDocument, ImportedMedia

logger = logging.getLogger(__name__)


def import_pdf(pdf_bytes: bytes, title: str | None = None) -> ImportedDocument:
    """Parse PDF bytes to ImportedDocument with TipTap JSON blocks.

    Heading detection: text lines with font size significantly larger
    than the median body font size are treated as headings. The heading
    level (1-3) is inferred from relative size.

    Args:
        pdf_bytes: Raw PDF file content.
        title: Override title. If ``None``, extracted from the first
            large-text line or the PDF metadata.
    """
    blocks: list[ImportedBlock] = []
    media: list[ImportedMedia] = []
    all_font_sizes: list[float] = []

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        # First pass: collect font sizes across all pages to compute median
        for page in pdf.pages:
            chars = page.chars or []
            for char in chars:
                size = char.get("size", 0)
                if size > 0:
                    all_font_sizes.append(size)

        if not all_font_sizes:
            # No extractable text - return empty doc
            return ImportedDocument(
                title=title or "Imported PDF",
                blocks=[],
                metadata={"source_format": "pdf"},
                media=[],
            )

        median_size = statistics.median(all_font_sizes)
        # Heading thresholds relative to median body size
        h1_threshold = median_size * 1.6
        h2_threshold = median_size * 1.3
        h3_threshold = median_size * 1.15

        doc_title = title
        extracted_title = None

        # Second pass: extract content page by page
        for page_idx, page in enumerate(pdf.pages):
            # Extract tables first so we can skip their regions in text
            page_tables = page.find_tables() or []
            table_bboxes = [t.bbox for t in page_tables]

            # Extract table content
            for table in page_tables:
                table_data = table.extract()
                if table_data:
                    blocks.append(_table_to_block(table_data))

            # Extract text lines, excluding table regions
            filtered_page = page
            for bbox in table_bboxes:
                filtered_page = filtered_page.outside_bbox(bbox)

            lines = _extract_lines(filtered_page)

            for line_text, line_size, is_bold in lines:
                text = line_text.strip()
                if not text:
                    continue

                # Detect heading by font size
                if line_size >= h1_threshold:
                    if extracted_title is None:
                        extracted_title = text
                    blocks.append(_heading_block(text, 1))
                elif line_size >= h2_threshold:
                    blocks.append(_heading_block(text, 2))
                elif line_size >= h3_threshold or is_bold:
                    # Bold standalone lines with short length are likely headings
                    if is_bold and len(text) < 100:
                        blocks.append(_heading_block(text, 3))
                    else:
                        blocks.append(_paragraph_block(text))
                else:
                    blocks.append(_paragraph_block(text))

            # Extract images from page
            for img_idx, img in enumerate(page.images or []):
                media.append(
                    ImportedMedia(
                        url=f"pdf-page-{page_idx + 1}-img-{img_idx + 1}",
                        file_name=f"page{page_idx + 1}_img{img_idx + 1}.png",
                        file_type="image/png",
                    )
                )

    # Merge consecutive paragraphs (PDFs often split single paragraphs across lines)
    blocks = _merge_consecutive_paragraphs(blocks)

    final_title = doc_title or extracted_title or "Imported PDF"

    return ImportedDocument(
        title=final_title,
        blocks=blocks,
        metadata={"source_format": "pdf", "page_count": len(pdf.pages) if pdf_bytes else 0},
        media=media,
    )


def _extract_lines(page: pdfplumber.page.Page) -> list[tuple[str, float, bool]]:
    """Extract text lines with their font size and bold status.

    Returns list of (text, dominant_font_size, is_bold) tuples.
    """
    chars = page.chars or []
    if not chars:
        return []

    # Group characters into lines by y-coordinate (within 2pt tolerance)
    lines_by_y: dict[float, list[dict]] = defaultdict(list)
    for char in chars:
        y_key = round(char.get("top", 0) / 2) * 2  # bucket by 2pt
        lines_by_y[y_key].append(char)

    result: list[tuple[str, float, bool]] = []
    for y_key in sorted(lines_by_y.keys()):
        line_chars = sorted(lines_by_y[y_key], key=lambda c: c.get("x0", 0))
        text = "".join(c.get("text", "") for c in line_chars)
        if not text.strip():
            continue

        sizes = [c.get("size", 0) for c in line_chars if c.get("size", 0) > 0]
        dominant_size = statistics.median(sizes) if sizes else 0

        # Detect bold from fontname
        bold_count = sum(1 for c in line_chars if "bold" in (c.get("fontname", "") or "").lower())
        is_bold = bold_count > len(line_chars) * 0.5

        result.append((text, dominant_size, is_bold))

    return result


def _heading_block(text: str, level: int) -> ImportedBlock:
    """Create a TipTap heading block."""
    return ImportedBlock(
        block_type="heading",
        content={
            "type": "heading",
            "attrs": {"level": level},
            "content": [{"type": "text", "text": text}],
        },
        heading_level=level,
    )


def _paragraph_block(text: str) -> ImportedBlock:
    """Create a TipTap paragraph block."""
    return ImportedBlock(
        block_type="paragraph",
        content={
            "type": "paragraph",
            "content": [{"type": "text", "text": text}],
        },
    )


def _table_to_block(table_data: list[list[str | None]]) -> ImportedBlock:
    """Convert extracted table data to TipTap table block."""
    rows = []
    for row_idx, row in enumerate(table_data):
        cells = []
        for cell_text in row:
            cell_content = cell_text or ""
            cell_type = "tableHeader" if row_idx == 0 else "tableCell"
            cells.append(
                {
                    "type": cell_type,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": cell_content}]
                            if cell_content
                            else [],
                        }
                    ],
                }
            )
        rows.append({"type": "tableRow", "content": cells})

    return ImportedBlock(
        block_type="table",
        content={"type": "table", "content": rows},
    )


def _merge_consecutive_paragraphs(blocks: list[ImportedBlock]) -> list[ImportedBlock]:
    """Merge consecutive short paragraph blocks that are likely parts of the same paragraph.

    PDFs often split a single paragraph across multiple lines. We merge
    consecutive paragraphs where neither ends with a sentence-ending
    punctuation mark.
    """
    if not blocks:
        return blocks

    merged: list[ImportedBlock] = []
    i = 0
    while i < len(blocks):
        block = blocks[i]
        if block.block_type != "paragraph":
            merged.append(block)
            i += 1
            continue

        # Accumulate text from consecutive paragraphs
        text_parts = [_get_block_text(block)]
        j = i + 1
        while j < len(blocks) and blocks[j].block_type == "paragraph":
            prev_text = text_parts[-1]
            # If previous line doesn't end with sentence-ending punctuation, merge
            if prev_text and not re.search(r"[.!?:]\s*$", prev_text):
                text_parts.append(_get_block_text(blocks[j]))
                j += 1
            else:
                break

        combined_text = " ".join(t for t in text_parts if t)
        merged.append(_paragraph_block(combined_text))
        i = j

    return merged


def _get_block_text(block: ImportedBlock) -> str:
    """Extract plain text from a TipTap block."""
    content = block.content
    if not content:
        return ""
    inner = content.get("content", [])
    return " ".join(node.get("text", "") for node in inner if isinstance(node, dict)).strip()
