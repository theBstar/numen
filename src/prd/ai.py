"""AI-powered PRD assistance: auto-complete, section editing, reviewer suggestions."""

from __future__ import annotations

import json
import logging
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_queries import (
    find_connected_entities,
    get_prd_impact_graph,
    get_prd_stakeholders,
)
from src.llm.client import call_llm
from src.prd.blocks import get_blocks
from src.shared.types import EntityType

logger = logging.getLogger(__name__)

# PRD sections the LLM should generate
PRD_SECTIONS = [
    "Overview",
    "Problem Statement",
    "Goals & Success Metrics",
    "User Stories",
    "Functional Requirements",
    "Non-Functional Requirements",
    "Technical Considerations",
    "Design Requirements",
    "Dependencies",
    "Rollout Plan",
    "Open Questions",
]


def _build_product_context(neighborhood: dict) -> str:
    """Extract product context from the graph neighborhood for prompt grounding."""
    entities = neighborhood.get("entities", [])
    neighborhood.get("edges", [])

    goals: list[str] = []
    features: list[str] = []
    related_prds: list[str] = []
    people: list[str] = []
    tasks: list[str] = []

    for entity in entities:
        etype = getattr(entity, "type", None) or entity.get("type", "")
        name = getattr(entity, "canonical_name", None) or entity.get("canonical_name", "")
        if not name:
            continue

        if etype in ("goal", EntityType.GOAL.value if hasattr(EntityType, "GOAL") else "goal"):
            goals.append(name)
        elif etype in ("feature", "document"):
            props = getattr(entity, "properties", None) or entity.get("properties", {})
            if isinstance(props, str):
                try:
                    props = json.loads(props)
                except (json.JSONDecodeError, TypeError):
                    props = {}
            node_type = props.get("node_type", "") if isinstance(props, dict) else ""
            if node_type == "document":
                related_prds.append(name)
            else:
                features.append(name)
        elif etype in ("person",):
            people.append(name)
        elif etype in ("task",):
            tasks.append(name)

    sections: list[str] = []
    if goals:
        sections.append("Goals:\n" + "\n".join(f"- {g}" for g in goals[:10]))
    if features:
        sections.append("Features:\n" + "\n".join(f"- {f}" for f in features[:10]))
    if related_prds:
        sections.append("Related PRDs:\n" + "\n".join(f"- {p}" for p in related_prds[:10]))
    if tasks:
        sections.append("Existing Tasks:\n" + "\n".join(f"- {t}" for t in tasks[:10]))
    if people:
        sections.append("Team Members:\n" + "\n".join(f"- {p}" for p in people[:10]))

    return "\n\n".join(sections) if sections else "No additional product context available."


def _parse_inline_marks(text: str) -> list[dict]:
    """Parse markdown inline formatting into TipTap text nodes with marks.

    Handles **bold**, *italic*, and `code` formatting. Falls back to
    plain text if parsing produces no results.
    """
    if not text:
        return [{"type": "text", "text": text}]

    nodes: list[dict] = []

    # Pattern matches: **bold**, *italic* (not **), or `code`
    # Order matters - bold (**) must be checked before italic (*)
    pattern = re.compile(
        r"(\*\*(.+?)\*\*)"  # bold
        r"|(\*(.+?)\*)"  # italic (single *)
        r"|(`(.+?)`)"  # code
    )

    last_end = 0
    for match in pattern.finditer(text):
        # Add any plain text before this match
        if match.start() > last_end:
            plain = text[last_end : match.start()]
            if plain:
                nodes.append({"type": "text", "text": plain})

        if match.group(2) is not None:
            # Bold match
            nodes.append(
                {
                    "type": "text",
                    "text": match.group(2),
                    "marks": [{"type": "bold"}],
                }
            )
        elif match.group(4) is not None:
            # Italic match
            nodes.append(
                {
                    "type": "text",
                    "text": match.group(4),
                    "marks": [{"type": "italic"}],
                }
            )
        elif match.group(6) is not None:
            # Code match
            nodes.append(
                {
                    "type": "text",
                    "text": match.group(6),
                    "marks": [{"type": "code"}],
                }
            )

        last_end = match.end()

    # Add any remaining plain text after the last match
    if last_end < len(text):
        remaining = text[last_end:]
        if remaining:
            nodes.append({"type": "text", "text": remaining})

    # Fallback - if regex produced nothing, return plain text
    if not nodes:
        return [{"type": "text", "text": text}]

    return nodes


def _section_to_tiptap_blocks(heading: str, content: str, start_position: float) -> list[dict]:
    """Convert a heading + content pair into TipTap JSON block dicts."""
    blocks: list[dict] = []
    position = start_position

    # Heading block
    blocks.append(
        {
            "block_type": "heading",
            "content": {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": heading}],
            },
            "heading_level": 2,
            "position": position,
            "ai_generated": True,
        }
    )
    position += 1.0

    # Split content into paragraphs
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [content.strip()] if content.strip() else [""]

    for para_text in paragraphs:
        # Check if it looks like a bullet list
        lines = para_text.split("\n")
        is_list = (
            all(
                line.strip().startswith("- ") or line.strip().startswith("* ")
                for line in lines
                if line.strip()
            )
            and len(lines) > 1
        )

        if is_list:
            list_items = []
            for line in lines:
                item_text = line.strip().lstrip("-* ").strip()
                if item_text:
                    list_items.append(
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": _parse_inline_marks(item_text),
                                }
                            ],
                        }
                    )
            if list_items:
                blocks.append(
                    {
                        "block_type": "bullet_list",
                        "content": {
                            "type": "bulletList",
                            "content": list_items,
                        },
                        "heading_level": None,
                        "position": position,
                        "ai_generated": True,
                    }
                )
                position += 1.0
        else:
            blocks.append(
                {
                    "block_type": "paragraph",
                    "content": {
                        "type": "paragraph",
                        "content": _parse_inline_marks(para_text),
                    },
                    "heading_level": None,
                    "position": position,
                    "ai_generated": True,
                }
            )
            position += 1.0

    return blocks


def _parse_llm_json(text: str) -> list[dict]:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
        logger.warning("LLM returned non-array JSON: %s", text[:200])
        return []
    except json.JSONDecodeError:
        logger.warning("Failed to parse LLM response as JSON: %s", text[:200])
        return []


async def auto_complete_prd(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    initial_prompt: str,
) -> list[dict]:
    """Generate full PRD content from an initial prompt/outline.

    1. Gather context from the graph:
       - Related PRDs (via folder siblings, shared goals)
       - Linked goals and their OKRs
       - Team members and roles
       - Existing features in the product
    2. Build a system prompt that includes product context
    3. Call LLM to generate structured PRD sections
    4. Return list of block operations (TipTap JSON) for each section
    """
    # 1. Gather context from the graph neighborhood (graceful fallback if graph fails)
    try:
        neighborhood = await get_prd_impact_graph(db, entity_id, depth=2, org_id=org_id)
    except Exception:
        logger.warning("Failed to fetch PRD graph context for %s, proceeding without it", entity_id)
        neighborhood = {"entities": [], "edges": []}
    product_context = _build_product_context(neighborhood)

    # Also fetch linked goals for richer context
    try:
        connected_goals = await find_connected_entities(
            db,
            entity_id,
            EntityType.GOAL,
            max_hops=2,
            org_id=org_id,
        )
    except Exception:
        logger.warning("Failed to fetch connected goals for %s", entity_id)
        connected_goals = []
    goal_names = []
    for g in connected_goals[:5]:
        name = getattr(g, "canonical_name", None) or g.get("canonical_name", "")
        if name:
            goal_names.append(name)

    if goal_names:
        product_context += "\n\nLinked Goals:\n" + "\n".join(f"- {g}" for g in goal_names)

    # 2. Build prompts
    sections_list = "\n".join(f"- {s}" for s in PRD_SECTIONS)

    system_prompt = (
        "You are a product manager writing a PRD (Product Requirements Document).\n\n"
        f"Context about the product:\n{product_context}\n\n"
        "The user wants to create a PRD with the initial description below.\n\n"
        "Generate a complete, detailed PRD with the following sections. "
        "For each section, provide rich content with specific details, "
        "not generic placeholders.\n\n"
        f"Sections:\n{sections_list}\n\n"
        "Return a JSON array where each item is a section:\n"
        '[{"heading": "Overview", "content": "...detailed paragraph..."}, '
        '{"heading": "Problem Statement", "content": "..."}, ...]\n\n'
        "Be specific and actionable. Reference existing product features and "
        "goals where relevant.\n"
        "Use **bold** for key terms and emphasis. "
        "Use *italics* for definitions and technical terms. "
        "Use `backticks` for code, APIs, and technical names.\n"
        "Use hyphens (-) not em dashes in all content.\n"
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = f"Create a PRD for:\n\n{initial_prompt}"

    # 3. Call LLM with JSON-focused prompt
    response_text = await call_llm(
        system=system_prompt,
        user=user_prompt,
        max_tokens=4096,
    )

    # 4. Parse response and convert to TipTap blocks
    sections = _parse_llm_json(response_text)
    if not sections:
        logger.error("LLM returned no valid sections for PRD auto-complete")
        return []

    all_blocks: list[dict] = []
    position = 0.0

    for section in sections:
        heading = section.get("heading", "")
        content = section.get("content", "")
        if not heading:
            continue

        blocks = _section_to_tiptap_blocks(heading, content, position)
        all_blocks.extend(blocks)
        position += len(blocks)

    logger.info(
        "Generated %d blocks across %d sections for PRD %s",
        len(all_blocks),
        len(sections),
        entity_id,
    )

    return all_blocks


async def edit_section(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    block_ids: list[UUID],
    instruction: str,
) -> list[dict]:
    """AI-edit specific blocks based on user instruction.

    1. Load the specified blocks
    2. Load surrounding context (nearby blocks for context)
    3. Call LLM with current content + instruction
    4. Return updated block content as TipTap JSON
    """
    # 1. Load all blocks for this PRD
    all_blocks = await get_blocks(db, org_id, entity_id)
    block_id_set = {str(bid) for bid in block_ids}

    # 2. Separate target blocks and gather surrounding context
    target_blocks: list[dict] = []
    target_positions: list[float] = []
    all_block_list = []

    for block in all_blocks:
        block_dict = {
            "id": str(block.id),
            "block_type": block.block_type,
            "content": block.content,
            "position": block.position,
            "heading_level": block.heading_level,
        }
        all_block_list.append(block_dict)

        if str(block.id) in block_id_set:
            target_blocks.append(block_dict)
            target_positions.append(block.position)

    if not target_blocks:
        logger.warning("No matching blocks found for edit_section: %s", block_ids)
        return []

    # Extract text content from target blocks
    def _extract_text(content: dict) -> str:
        parts: list[str] = []
        if "text" in content:
            parts.append(content["text"])
        for child in content.get("content", []):
            if isinstance(child, dict):
                parts.append(_extract_text(child))
        return " ".join(parts).strip()

    current_text_parts = []
    for block in target_blocks:
        text = _extract_text(block["content"])
        if text:
            current_text_parts.append(text)
    current_text = "\n\n".join(current_text_parts)

    # Get surrounding context (blocks before and after the selection)
    if target_positions:
        min_pos = min(target_positions)
        max_pos = max(target_positions)

        context_before = []
        context_after = []
        for block in all_block_list:
            text = _extract_text(block["content"])
            if not text:
                continue
            if block["position"] < min_pos:
                context_before.append(text)
            elif block["position"] > max_pos and str(block["id"]) not in block_id_set:
                context_after.append(text)

        # Keep only the nearest context
        context_before = context_before[-3:]
        context_after = context_after[:3]
    else:
        context_before = []
        context_after = []

    surrounding_context = ""
    if context_before:
        surrounding_context += "Content before:\n" + "\n".join(context_before) + "\n\n"
    if context_after:
        surrounding_context += "Content after:\n" + "\n".join(context_after)

    # 3. Build prompts
    system_prompt = (
        "You are editing a section of a PRD document.\n\n"
        f"Current section content:\n{current_text}\n\n"
    )
    if surrounding_context:
        system_prompt += f"Surrounding context:\n{surrounding_context}\n\n"

    system_prompt += (
        "Return the edited section as a JSON array of TipTap paragraph nodes:\n"
        '[{"type": "paragraph", "content": [{"type": "text", "text": "..."}]}]\n\n'
        "Preserve the overall structure. Only modify what the instruction asks for.\n"
        "Use hyphens (-) not em dashes in all content.\n"
        "Return ONLY the JSON array, no other text."
    )

    user_prompt = f"Edit instruction: {instruction}"

    # 4. Call LLM
    response_text = await call_llm(
        system=system_prompt,
        user=user_prompt,
        max_tokens=2048,
    )

    # 5. Parse and convert to block format
    parsed_nodes = _parse_llm_json(response_text)
    if not parsed_nodes:
        logger.error("LLM returned no valid content for section edit")
        return []

    # Use the position of the first target block as the starting position
    start_position = target_positions[0] if target_positions else 0.0
    result_blocks: list[dict] = []

    for i, node in enumerate(parsed_nodes):
        node_type = node.get("type", "paragraph")

        # Map TipTap type to block_type
        type_map = {
            "paragraph": "paragraph",
            "heading": "heading",
            "bulletList": "bullet_list",
            "orderedList": "ordered_list",
            "codeBlock": "code_block",
            "blockquote": "blockquote",
        }
        block_type = type_map.get(node_type, "paragraph")

        heading_level = None
        if block_type == "heading":
            attrs = node.get("attrs", {})
            heading_level = attrs.get("level", 2)

        result_blocks.append(
            {
                "block_type": block_type,
                "content": node,
                "heading_level": heading_level,
                "position": start_position + (i * 0.1),
                "ai_generated": True,
            }
        )

    logger.info(
        "Edited %d blocks into %d blocks for PRD %s",
        len(target_blocks),
        len(result_blocks),
        entity_id,
    )

    return result_blocks


async def suggest_reviewers(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> list[dict]:
    """Suggest reviewers based on graph relationships.

    Find people who:
    1. Own goals this PRD is tagged to (TAGGED_TO -> Goal <- OWNS)
    2. Authored related PRDs (sibling docs via shared goals)
    3. Are assigned to tasks that would implement this (IMPLEMENTS edges)
    4. Are team leads of affected projects

    Return ranked list with reasoning. Pure graph traversal - no LLM needed.
    """
    from src.graph.falkor_client import get_org_graph

    graph = await get_org_graph(org_id)
    eid = str(entity_id)

    candidates: dict[str, dict] = {}  # person_id -> {name, reasons, score}

    # 1. Goal owners - people who own goals this PRD is tagged to
    goal_owner_result = await graph.query(
        "MATCH (d:Document {id: $id})-[:TAGGED_TO]->(g:Goal)<-[:OWNS]-(p:Person) "
        "RETURN p.id AS pid, p.canonical_name AS pname, g.canonical_name AS gname",
        {"id": eid},
    )
    for row in goal_owner_result.result_set:
        pid = row[0]
        if pid not in candidates:
            candidates[pid] = {"person_name": row[1] or "Unknown", "reasons": [], "score": 0.0}
        candidates[pid]["reasons"].append(f"Owns goal: {row[2]}")
        candidates[pid]["score"] += 3.0

    # 2. Authors of related PRDs (same goals)
    related_author_result = await graph.query(
        "MATCH (d:Document {id: $id})-[:TAGGED_TO]->(g:Goal)<-[:TAGGED_TO]-(sibling:Document) "
        "WHERE sibling.id <> $id "
        "MATCH (p:Person)-[:OWNS]->(sibling) "
        "RETURN DISTINCT p.id AS pid, p.canonical_name AS pname, sibling.canonical_name AS sname",
        {"id": eid},
    )
    for row in related_author_result.result_set:
        pid = row[0]
        if pid not in candidates:
            candidates[pid] = {"person_name": row[1] or "Unknown", "reasons": [], "score": 0.0}
        candidates[pid]["reasons"].append(f"Authored related PRD: {row[2]}")
        candidates[pid]["score"] += 2.0

    # 3. People assigned to implementing tasks
    implementer_result = await graph.query(
        "MATCH (t:Task)-[:IMPLEMENTS]->(d:Document {id: $id}) "
        "MATCH (p:Person)-[:OWNS|ASSIGNED_TO]->(t) "
        "RETURN DISTINCT p.id AS pid, p.canonical_name AS pname, count(t) AS task_count",
        {"id": eid},
    )
    for row in implementer_result.result_set:
        pid = row[0]
        if pid not in candidates:
            candidates[pid] = {"person_name": row[1] or "Unknown", "reasons": [], "score": 0.0}
        candidates[pid]["reasons"].append(f"Assigned to {row[2]} implementing task(s)")
        candidates[pid]["score"] += 1.5

    # 4. Team leads of related projects
    lead_result = await graph.query(
        "MATCH (d:Document {id: $id})-[:TAGGED_TO]->(g:Goal)<-[:TAGGED_TO]-(t:Task) "
        "MATCH (proj:Project)-[:CONTAINS]->(t) "
        "MATCH (p:Person)-[:OWNS]->(proj) "
        "RETURN DISTINCT p.id AS pid, p.canonical_name AS pname, proj.canonical_name AS projname",
        {"id": eid},
    )
    for row in lead_result.result_set:
        pid = row[0]
        if pid not in candidates:
            candidates[pid] = {"person_name": row[1] or "Unknown", "reasons": [], "score": 0.0}
        candidates[pid]["reasons"].append(f"Leads project: {row[2]}")
        candidates[pid]["score"] += 2.5

    # Filter out the PRD owner themselves (they don't need to review their own doc)
    current_stakeholders = await get_prd_stakeholders(db, entity_id, org_id=org_id)
    owner_ids = {s["person_id"] for s in current_stakeholders if s["role_type"] == "owner"}
    existing_reviewer_ids = {
        s["person_id"] for s in current_stakeholders if s["role_type"] == "reviewer"
    }

    # Build ranked result list
    result: list[dict] = []
    for pid, info in candidates.items():
        if pid in owner_ids:
            continue
        if pid in existing_reviewer_ids:
            continue

        # Combine reasons into a single string
        reason = "; ".join(info["reasons"][:3])
        result.append(
            {
                "member_id": pid,
                "person_name": info["person_name"],
                "reason": reason,
                "score": round(info["score"], 1),
            }
        )

    # Sort by score descending
    result.sort(key=lambda x: x["score"], reverse=True)

    logger.info(
        "Suggested %d reviewers for PRD %s",
        len(result),
        entity_id,
    )

    return result[:10]  # Return top 10 suggestions
