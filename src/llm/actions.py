"""Dispatchable Claude actions for the Numen platform.

Every action returns ``draft: True`` - nothing is executed without human
approval.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import get_edges, get_entities_by_ids, get_entity
from src.llm.client import call_llm_with_trace
from src.llm.prompts import build_briefing_narrative_prompt, build_pr_summary_prompt
from src.shared.provenance import LLMTrace
from src.shared.types import BriefingItem, EdgeType, EntityType, RoleType

logger = logging.getLogger(__name__)


async def summarize_pr_diff(
    db: AsyncSession, pr_entity_id: UUID, *, org_id: UUID | None = None
) -> dict:
    """Summarize a pull-request diff using Claude.

    Steps:
        1. Fetch the PR Entity from the database.
        2. Get linked task entities via SHIPS_TO / TAGGED_TO edges.
        3. Extract diff_text from ``entity.properties["diff"]``.
        4. Build the prompt and call Claude.
        5. Return a draft summary dict.

    Returns:
        A dict with keys ``summary``, ``draft``, ``pr_title``, ``entity_id``,
        and ``llm_trace`` for provenance.
    """
    # 1. Fetch the PR entity
    pr_entity = await get_entity(db, pr_entity_id, org_id=org_id)
    if pr_entity is None or pr_entity.type != EntityType.COMMIT_PR:
        raise ValueError(f"PR entity not found: {pr_entity_id}")

    # 2. Find linked task entities via SHIPS_TO or TAGGED_TO edges
    edges = await get_edges(
        db, pr_entity_id, edge_types=[EdgeType.SHIPS_TO, EdgeType.TAGGED_TO], direction="outgoing"
    )

    linked_tasks: list[dict] = []
    if edges:
        task_ids = [edge.to_entity_id for edge in edges]
        task_entities = await get_entities_by_ids(db, task_ids, org_id=org_id)
        task_entities = [t for t in task_entities if t.type == EntityType.TASK]

        for task in task_entities:
            props = task.properties or {}
            linked_tasks.append(
                {
                    "title": task.canonical_name,
                    "goal_tags": props.get("goal_tags", []),
                    "status": props.get("status", ""),
                }
            )

    # 3. Extract diff text from PR properties
    pr_props = pr_entity.properties or {}
    diff_text = pr_props.get("diff", "")
    pr_title = pr_entity.canonical_name
    pr_description = pr_props.get("description", "")

    # 4. Build the prompt and call Claude
    file_history = pr_props.get("file_history")
    system_prompt, user_prompt = build_pr_summary_prompt(
        pr_title=pr_title,
        pr_description=pr_description,
        diff_text=diff_text,
        linked_tasks=linked_tasks,
        file_history=file_history,
    )

    # Collect entity IDs used as grounding context
    grounding_ids = [str(pr_entity_id)]
    grounding_ids.extend(str(edge.to_entity_id) for edge in edges)

    response = await call_llm_with_trace(system=system_prompt, user=user_prompt)

    # Build LLM provenance trace
    llm_trace = LLMTrace(
        model=response.model,
        prompt_summary=f"PR summary for '{pr_title}' with {len(linked_tasks)} linked task(s)",
        input_entities=grounding_ids,
        input_token_count=response.input_token_count,
        output_token_count=response.output_token_count,
        reasoning=response.text,
        grounding_entities=grounding_ids,
        latency_ms=response.latency_ms,
    )

    # 5. Return draft result - never auto-published
    return {
        "summary": response.text,
        "draft": True,
        "pr_title": pr_title,
        "entity_id": str(pr_entity_id),
        "llm_trace": llm_trace.model_dump(),
    }


async def generate_briefing_narrative(
    items: list[BriefingItem],
    role: RoleType,
    person_name: str,
) -> dict:
    """Generate a morning-briefing narrative for a person.

    Converts ``BriefingItem`` instances to dicts, builds the prompt, calls
    Claude, and returns a dict with the narrative string and an LLM trace.
    """
    # 1. Convert BriefingItems to dicts for the prompt
    item_dicts = [
        {
            "title": item.title,
            "urgency_score": item.urgency_score,
            "why_it_matters": item.why_it_matters,
            "goal_tags": item.goal_tags,
            "entity_type": item.entity_type.value,
            "suggested_action": item.suggested_action,
        }
        for item in items
    ]

    # Collect entity IDs used as input context
    input_entity_ids = [str(item.entity_id) for item in items]

    # 2. Build the prompt
    system_prompt, user_prompt = build_briefing_narrative_prompt(
        items=item_dicts,
        role=role.value,
        person_name=person_name,
    )

    # 3. Call Claude with trace and build provenance
    response = await call_llm_with_trace(system=system_prompt, user=user_prompt)

    llm_trace = LLMTrace(
        model=response.model,
        prompt_summary=(
            f"Briefing narrative for {person_name} ({role.value}) with {len(items)} item(s)"
        ),
        input_entities=input_entity_ids,
        input_token_count=response.input_token_count,
        output_token_count=response.output_token_count,
        reasoning=response.text,
        grounding_entities=input_entity_ids,
        latency_ms=response.latency_ms,
    )

    return {
        "narrative": response.text,
        "llm_trace": llm_trace.model_dump(),
    }
