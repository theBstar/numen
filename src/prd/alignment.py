"""PR-PRD alignment checking.

When a PR lands via GitHub sync, traces it through the graph:
PR -> SHIPS_TO -> Task -> IMPLEMENTS -> PRD

For each linked PRD, compares the PR changes against PRD requirements
to detect spec gaps, label mismatches, and missing features.
"""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_client import get_org_graph as _get_graph
from src.graph.falkor_repository import _node_to_entity
from src.llm.client import call_llm_with_trace
from src.shared.models import PrdAlignmentCheck, PrdBlock
from src.shared.provenance import LLMTrace

logger = logging.getLogger(__name__)

# ── LLM prompt ──────────────────────────────────────────────────────────

_ALIGNMENT_SYSTEM_PROMPT = """\
You are a code reviewer checking if a Pull Request properly implements \
the requirements from a PRD.

PRD Title: {prd_title}
PRD Sections and Requirements:
{prd_sections}

Pull Request:
Title: {pr_title}
Description: {pr_description}
Changed files: {file_list}

Analyze the PR against the PRD and identify any gaps or mismatches.
Return a JSON object:
{{
  "findings": [
    {{
      "type": "missing_requirement" | "label_mismatch" | "assumption_conflict" | "scope_drift",
      "prd_section": "section heading where the requirement comes from",
      "detail": "specific description of what is missing or wrong",
      "severity": "high" | "medium" | "low"
    }}
  ],
  "coverage_score": 0.0 to 1.0
}}

Types:
- missing_requirement: PRD specifies something the PR does not address
- label_mismatch: PRD uses one term/label but PR uses a different one
- assumption_conflict: PR implementation contradicts a PRD assumption
- scope_drift: PR implements something not in the PRD scope

Only flag genuine issues. If the PR fully covers the PRD requirements, \
return empty findings and a coverage_score of 1.0.
Use hyphens (-) not em dashes.
Return ONLY valid JSON, no markdown fences or extra text."""

_ALIGNMENT_USER_PROMPT = "Analyze the PR against the PRD and return JSON."


# ── Graph traversal helpers ─────────────────────────────────────────────


async def _find_linked_prds(org_id: UUID, pr_entity_id: str) -> list[dict]:
    """Traverse PR -> SHIPS_TO -> Task -> IMPLEMENTS -> Document.

    Returns a list of dicts with ``{prd_id, prd_title}`` for each linked PRD.
    """
    graph = await _get_graph(org_id)

    result = await graph.query(
        "MATCH (pr:CommitPR {id: $pr_id})-[:SHIPS_TO]->(t:Task)"
        "-[:IMPLEMENTS]->(d:Document) "
        "RETURN DISTINCT d.id AS prd_id, d.canonical_name AS prd_title",
        {"pr_id": pr_entity_id},
    )

    prds: list[dict] = []
    for row in result.result_set:
        prds.append({"prd_id": row[0], "prd_title": row[1]})
    return prds


async def _get_pr_summary(org_id: UUID, pr_entity_id: str) -> dict:
    """Fetch PR title, description, and changed files from FalkorDB."""
    graph = await _get_graph(org_id)

    result = await graph.query(
        "MATCH (pr:CommitPR {id: $pr_id}) RETURN pr",
        {"pr_id": pr_entity_id},
    )
    if not result.result_set:
        return {"title": "", "description": "", "changed_files": []}

    pr = _node_to_entity(result.result_set[0][0])
    props = pr.properties if hasattr(pr, "properties") else {}
    if isinstance(props, str):
        try:
            props = json.loads(props)
        except (json.JSONDecodeError, TypeError):
            props = {}
    if not isinstance(props, dict):
        props = {}

    return {
        "title": pr.canonical_name if hasattr(pr, "canonical_name") else "",
        "description": props.get("description", ""),
        "changed_files": props.get("changed_files", []),
    }


async def _get_prd_sections(
    db: AsyncSession,
    org_id: UUID,
    prd_entity_id: str,
) -> list[dict]:
    """Load PRD block headings and key content from PostgreSQL."""
    from uuid import UUID as _UUID

    try:
        entity_uuid = _UUID(prd_entity_id)
    except (ValueError, AttributeError):
        return []

    stmt = (
        select(PrdBlock)
        .where(
            PrdBlock.org_id == org_id,
            PrdBlock.entity_id == entity_uuid,
        )
        .order_by(PrdBlock.position)
    )
    result = await db.execute(stmt)
    blocks = result.scalars().all()

    sections: list[dict] = []
    for block in blocks:
        content = block.content or {}
        # Extract plain text from TipTap JSON
        text = _extract_text_from_tiptap(content)
        if text.strip():
            sections.append(
                {
                    "slug": block.slug,
                    "block_type": block.block_type,
                    "heading_level": block.heading_level,
                    "text": text[:500],  # Limit per-section to avoid token bloat
                }
            )
    return sections


def _extract_text_from_tiptap(content: dict) -> str:
    """Recursively extract plain text from TipTap JSON content."""
    if not content or not isinstance(content, dict):
        return ""

    parts: list[str] = []

    # Direct text node
    if content.get("type") == "text":
        parts.append(content.get("text", ""))

    # Recurse into children
    for child in content.get("content", []):
        if isinstance(child, dict):
            parts.append(_extract_text_from_tiptap(child))

    return " ".join(parts)


# ── Core alignment check ───────────────────────────────────────────────


async def check_pr_alignment(
    db: AsyncSession,
    org_id: UUID,
    pr_entity_id: UUID,
) -> list[dict]:
    """Check a PR against its linked PRDs.

    1. Find linked PRDs: PR -> SHIPS_TO -> Task -> IMPLEMENTS -> Document
    2. For each PRD:
       a. Load PRD section headings and key content
       b. Get PR summary (title, description, changed files)
       c. Call LLM to compare and find gaps
       d. Store findings as PrdAlignmentCheck record
    3. Return all findings
    """
    pr_id_str = str(pr_entity_id)

    # 1. Find linked PRDs via graph traversal
    linked_prds = await _find_linked_prds(org_id, pr_id_str)
    if not linked_prds:
        logger.debug(
            "No linked PRDs found for PR %s in org %s",
            pr_entity_id,
            org_id,
        )
        return []

    # 2. Get PR summary
    pr_summary = await _get_pr_summary(org_id, pr_id_str)
    if not pr_summary["title"]:
        logger.warning("PR entity %s has no title, skipping alignment check", pr_entity_id)
        return []

    all_findings: list[dict] = []

    for prd in linked_prds:
        prd_id = prd["prd_id"]
        prd_title = prd["prd_title"] or "Untitled PRD"

        # 2a. Load PRD sections
        sections = await _get_prd_sections(db, org_id, prd_id)
        if not sections:
            logger.debug("No blocks found for PRD %s, skipping", prd_id)
            continue

        # 2b. Format sections for prompt
        sections_text = "\n".join(f"- [{s['block_type']}] {s['text']}" for s in sections)

        file_list = ", ".join(pr_summary["changed_files"][:50]) or "(no files listed)"

        # 2c. Call LLM
        system_prompt = _ALIGNMENT_SYSTEM_PROMPT.format(
            prd_title=prd_title,
            prd_sections=sections_text,
            pr_title=pr_summary["title"],
            pr_description=pr_summary["description"][:1000] or "(no description)",
            file_list=file_list,
        )

        try:
            response = await call_llm_with_trace(
                system=system_prompt,
                user=_ALIGNMENT_USER_PROMPT,
                max_tokens=2048,
            )

            # Parse JSON response
            result = _parse_llm_response(response.text)
            findings = result.get("findings", [])
            coverage_score = result.get("coverage_score")

            # Build LLM trace for provenance
            llm_trace = LLMTrace(
                model=response.model,
                prompt_summary=(
                    f"PRD alignment check: PR '{pr_summary['title']}' vs PRD '{prd_title}'"
                ),
                input_entities=[pr_id_str, prd_id],
                input_token_count=response.input_token_count,
                output_token_count=response.output_token_count,
                reasoning=response.text,
                grounding_entities=[pr_id_str, prd_id],
                latency_ms=response.latency_ms,
            )

            # 2d. Store as PrdAlignmentCheck record
            from uuid import UUID as _UUID

            try:
                prd_uuid = _UUID(prd_id) if isinstance(prd_id, str) else prd_id
            except (ValueError, AttributeError):
                logger.warning("Invalid PRD entity ID: %s", prd_id)
                continue

            check = PrdAlignmentCheck(
                org_id=org_id,
                prd_entity_id=prd_uuid,
                pr_entity_id=pr_entity_id,
                findings=findings,
                coverage_score=coverage_score,
                status="pending" if findings else "resolved",
            )
            db.add(check)
            await db.flush()

            finding_result = {
                "check_id": str(check.id),
                "prd_entity_id": str(prd_uuid),
                "prd_title": prd_title,
                "pr_entity_id": str(pr_entity_id),
                "pr_title": pr_summary["title"],
                "findings": findings,
                "coverage_score": coverage_score,
                "llm_trace": llm_trace.model_dump(),
            }
            all_findings.append(finding_result)

            logger.info(
                "Alignment check for PR %s vs PRD %s: %d finding(s), coverage=%.2f",
                pr_entity_id,
                prd_id,
                len(findings),
                coverage_score if coverage_score is not None else 0.0,
            )

        except Exception:
            logger.exception(
                "Failed alignment check for PR %s vs PRD %s",
                pr_entity_id,
                prd_id,
            )
            continue

    return all_findings


def _parse_llm_response(text: str) -> dict:
    """Parse LLM JSON response, tolerating markdown fences."""
    cleaned = text.strip()
    # Strip markdown code fences
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first line (```json or ```) and last line (```)
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM alignment response as JSON")
        return {"findings": [], "coverage_score": None}


# ── Batch check for sync ───────────────────────────────────────────────


async def check_alignment_for_sync(
    db: AsyncSession,
    org_id: UUID,
    pr_entity_ids: list[UUID],
) -> list[dict]:
    """Check alignment for multiple PRs after a sync.

    Called by the SyncCompleted event handler. Processes PRs sequentially
    to avoid overwhelming the LLM API on large syncs.
    """
    all_findings: list[dict] = []
    for pr_id in pr_entity_ids:
        findings = await check_pr_alignment(db, org_id, pr_id)
        all_findings.extend(findings)
    return all_findings


# ── Query helpers ──────────────────────────────────────────────────────


async def get_alignment_checks(
    db: AsyncSession,
    org_id: UUID,
    prd_entity_id: UUID | None = None,
) -> list[PrdAlignmentCheck]:
    """Get alignment check results, optionally filtered by PRD."""
    stmt = select(PrdAlignmentCheck).where(PrdAlignmentCheck.org_id == org_id)
    if prd_entity_id is not None:
        stmt = stmt.where(PrdAlignmentCheck.prd_entity_id == prd_entity_id)

    stmt = stmt.order_by(PrdAlignmentCheck.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def acknowledge_finding(
    db: AsyncSession,
    org_id: UUID,
    check_id: UUID,
) -> None:
    """Mark an alignment check as acknowledged."""
    stmt = (
        update(PrdAlignmentCheck)
        .where(
            PrdAlignmentCheck.id == check_id,
            PrdAlignmentCheck.org_id == org_id,
        )
        .values(status="acknowledged")
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Alignment check not found")


async def resolve_finding(
    db: AsyncSession,
    org_id: UUID,
    check_id: UUID,
) -> None:
    """Mark an alignment check as resolved."""
    stmt = (
        update(PrdAlignmentCheck)
        .where(
            PrdAlignmentCheck.id == check_id,
            PrdAlignmentCheck.org_id == org_id,
        )
        .values(status="resolved")
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Alignment check not found")
