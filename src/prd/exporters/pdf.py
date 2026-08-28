"""PDF exporter - convert TipTap JSON blocks to PDF bytes.

Uses weasyprint to convert styled HTML to PDF. Includes a cover page
with document metadata, page numbers, and a table of contents.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def export_to_pdf(
    title: str,
    blocks: list[dict],
    metadata: dict | None = None,
) -> bytes:
    """Convert TipTap JSON blocks to PDF bytes.

    Generates styled HTML via export_to_html, then converts to PDF
    using weasyprint. Adds a cover page, page numbers, and a ToC.

    Args:
        title: Document title.
        blocks: List of TipTap block dicts.
        metadata: Optional metadata dict.

    Returns:
        PDF file content as bytes.

    Raises:
        ImportError: If weasyprint is not installed.
    """
    try:
        from weasyprint import HTML as WeasyHTML  # noqa: N811
    except ImportError:
        raise ImportError(
            "weasyprint is required for PDF export. Install it with: pip install weasyprint"
        )

    from src.prd.exporters.html import export_to_html

    # Generate styled HTML
    html_content = export_to_html(title, blocks, metadata=metadata, styled=True)

    # Inject PDF-specific styles (cover page, page numbers, print tweaks)
    pdf_styles = _get_pdf_styles(title, metadata)
    html_content = html_content.replace("</style>", f"{pdf_styles}\n</style>")

    # Inject cover page before the document content
    cover_html = _build_cover_page(title, metadata)
    html_content = html_content.replace(
        '<div class="document">',
        f'{cover_html}\n<div class="document">',
    )

    # Convert to PDF
    html_doc = WeasyHTML(string=html_content)
    pdf_bytes = html_doc.write_pdf()

    return pdf_bytes


def _get_pdf_styles(title: str, metadata: dict | None) -> str:
    """Return CSS for PDF-specific layout (page margins, numbers, print)."""
    return """
/* PDF-specific styles */
@page {
  size: A4;
  margin: 2.5cm 2cm;
  @bottom-center {
    content: counter(page) " / " counter(pages);
    font-size: 9pt;
    color: #6B7280;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
  @bottom-right {
    content: "Numen";
    font-size: 9pt;
    color: #9CA3AF;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
}

@page :first {
  @bottom-center { content: none; }
  @bottom-right { content: none; }
}

.cover-page {
  page-break-after: always;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
  text-align: center;
  padding: 60px 40px;
}

.cover-page .cover-title {
  font-size: 2.5em;
  font-weight: 700;
  color: #1F2937;
  margin-bottom: 24px;
  line-height: 1.2;
}

.cover-page .cover-subtitle {
  font-size: 1.2em;
  color: #6B7280;
  margin-bottom: 48px;
  max-width: 500px;
}

.cover-page .cover-meta {
  display: grid;
  grid-template-columns: auto auto;
  gap: 8px 24px;
  font-size: 0.95em;
  text-align: left;
  margin-top: 32px;
}

.cover-page .cover-meta-label {
  font-weight: 600;
  color: #6B7280;
}

.cover-page .cover-meta-value {
  color: #1F2937;
}

.cover-page .cover-brand {
  margin-top: 64px;
  font-size: 1.1em;
  font-weight: 600;
  color: #4F46E5;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.cover-page .cover-divider {
  width: 80px;
  height: 4px;
  background: #4F46E5;
  margin: 24px auto;
  border-radius: 2px;
}

/* Print tweaks */
pre { white-space: pre-wrap; word-wrap: break-word; }
table { page-break-inside: avoid; }
h1, h2, h3 { page-break-after: avoid; }
img { page-break-inside: avoid; max-width: 100%; }
"""


def _build_cover_page(title: str, metadata: dict | None) -> str:
    """Build HTML for the PDF cover page."""
    import html as html_mod

    def esc(s: str) -> str:
        return html_mod.escape(s, quote=True)

    lines = ['<div class="cover-page">']
    lines.append('  <div class="cover-brand">Numen</div>')
    lines.append('  <div class="cover-divider"></div>')
    lines.append(f'  <div class="cover-title">{esc(title)}</div>')

    if metadata and metadata.get("description"):
        lines.append(f'  <div class="cover-subtitle">{esc(metadata["description"])}</div>')

    if metadata:
        lines.append('  <div class="cover-meta">')

        if metadata.get("status"):
            lines.append('    <span class="cover-meta-label">Status</span>')
            lines.append(f'    <span class="cover-meta-value">{esc(metadata["status"])}</span>')

        if metadata.get("owner"):
            lines.append('    <span class="cover-meta-label">Owner</span>')
            lines.append(f'    <span class="cover-meta-value">{esc(metadata["owner"])}</span>')

        if metadata.get("priority"):
            lines.append('    <span class="cover-meta-label">Priority</span>')
            lines.append(f'    <span class="cover-meta-value">{esc(metadata["priority"])}</span>')

        if metadata.get("target_date"):
            lines.append('    <span class="cover-meta-label">Target Date</span>')
            lines.append(
                f'    <span class="cover-meta-value">{esc(str(metadata["target_date"]))}</span>'
            )

        lines.append("  </div>")

    lines.append("</div>")
    return "\n".join(lines)
