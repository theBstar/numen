"""Generate rich AI coding prompts from task context.

Gathers data from the context graph (goals, blocking chain, PRs, project,
urgency) and assembles a structured prompt, then refines it via LLM.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import (
    compute_goal_progress,
    get_blocking_chain,
    get_entities_via_edge,
    get_entity,
    get_project_stats,
)
from src.llm.client import call_llm_with_trace
from src.llm.prompts import build_prompt_refinement_prompt, build_task_prompt_template
from src.mcp.serializers import entity_to_dict
from src.shared.models import UrgencyScoreCache
from src.shared.provenance import LLMTrace
from src.shared.types import EdgeType, EntityType

logger = logging.getLogger(__name__)


async def generate_task_prompt(
    db: AsyncSession,
    task_id: UUID,
    org_id: UUID,
) -> dict:
    """Generate a comprehensive AI coding prompt for a task.

    Steps:
        1. Gather context from the graph (template-based, instant)
        2. Assemble a structured markdown prompt
        3. Refine with LLM for better prioritization and actionability

    Returns:
        Dict with prompt, raw_prompt, task_title, repo_urls,
        has_blocking_chain, goal_count, and llm_trace.
    """
    # 1. Fetch the task entity
    task_entity = await get_entity(db, task_id, org_id=org_id)
    if task_entity is None or task_entity.type != EntityType.TASK:
        raise ValueError(f"Task not found: {task_id}")

    task_dict = entity_to_dict(task_entity)
    task_dict["source_ids"] = task_entity.source_ids or {}

    # 2. Linked goals via TAGGED_TO
    goal_entities = await get_entities_via_edge(
        db,
        task_id,
        EdgeType.TAGGED_TO,
        direction="outgoing",
        target_type=EntityType.GOAL,
        org_id=org_id,
    )
    goals = []
    for g in goal_entities:
        progress = await compute_goal_progress(db, g.id, org_id=org_id)
        goals.append({"name": g.canonical_name, "progress": progress, **entity_to_dict(g)})

    # 3. Blocking chain
    chain_entities = await get_blocking_chain(db, task_id)
    blocking_chain = []
    for e in chain_entities:
        props = e.properties or {}
        blocking_chain.append(
            {
                "name": e.canonical_name,
                "status": props.get("status", ""),
            }
        )

    # 4. Related PRs via SHIPS_TO (incoming)
    pr_entities = await get_entities_via_edge(
        db,
        task_id,
        EdgeType.SHIPS_TO,
        direction="incoming",
        target_type=EntityType.COMMIT_PR,
        org_id=org_id,
    )
    related_prs = [entity_to_dict(pr) for pr in pr_entities]

    # 5. Project context via CONTAINS (incoming)
    project_entities = await get_entities_via_edge(
        db,
        task_id,
        EdgeType.CONTAINS,
        direction="incoming",
        target_type=EntityType.PROJECT,
        org_id=org_id,
    )
    project = None
    if project_entities:
        proj = project_entities[0]
        stats = await get_project_stats(db, proj.id, org_id=org_id)
        project = {**entity_to_dict(proj), "stats": stats}

    # 6. Assignee via ASSIGNED_TO or OWNS
    assignee = None
    for edge_type in (EdgeType.ASSIGNED_TO, EdgeType.OWNS):
        assignee_entities = await get_entities_via_edge(
            db,
            task_id,
            edge_type,
            direction="incoming",
            target_type=EntityType.PERSON,
            org_id=org_id,
        )
        if assignee_entities:
            assignee = entity_to_dict(assignee_entities[0])
            break

    # 7. Urgency score
    stmt = (
        select(UrgencyScoreCache)
        .where(
            UrgencyScoreCache.entity_id == task_id,
            UrgencyScoreCache.org_id == org_id,
        )
        .limit(1)
    )
    score_result = await db.execute(stmt)
    score_row = score_result.scalar_one_or_none()
    urgency = None
    if score_row:
        urgency = {
            "score": score_row.score,
            "provenance": score_row.provenance or [],
            "components": score_row.score_components or {},
        }

    # 8. Build the template prompt
    raw_prompt = build_task_prompt_template(
        task=task_dict,
        goals=goals,
        blocking_chain=blocking_chain,
        related_prs=related_prs,
        project=project,
        urgency=urgency,
        assignee=assignee,
    )

    # 9. Extract repo URLs
    repo_urls: list[str] = []
    for pr in related_prs:
        pr_props = pr.get("properties", {})
        url = pr_props.get("html_url", "")
        if url:
            parts = url.split("/pull/")
            if len(parts) == 2:
                repo_url = parts[0]
                if repo_url not in repo_urls:
                    repo_urls.append(repo_url)

    # 10. Refine with LLM
    llm_trace_dict = None
    refined_prompt = raw_prompt  # Fallback if LLM fails

    try:
        system_prompt, user_prompt = build_prompt_refinement_prompt(raw_prompt)

        grounding_ids = [str(task_id)]
        grounding_ids.extend(str(g["id"]) for g in goals)

        response = await call_llm_with_trace(system=system_prompt, user=user_prompt)
        refined_prompt = response.text

        llm_trace = LLMTrace(
            model=response.model,
            prompt_summary=(
                f"Prompt refinement for '{task_entity.canonical_name}' "
                f"with {len(goals)} goal(s), {len(blocking_chain)} blocker(s)"
            ),
            input_entities=grounding_ids,
            input_token_count=response.input_token_count,
            output_token_count=response.output_token_count,
            reasoning=response.text[:200],
            grounding_entities=grounding_ids,
            latency_ms=response.latency_ms,
        )
        llm_trace_dict = llm_trace.model_dump()
    except Exception:
        logger.warning("LLM refinement failed, falling back to template prompt", exc_info=True)

    return {
        "prompt": refined_prompt,
        "raw_prompt": raw_prompt,
        "task_title": task_entity.canonical_name,
        "repo_urls": repo_urls,
        "has_blocking_chain": len(blocking_chain) > 0,
        "goal_count": len(goals),
        "llm_trace": llm_trace_dict,
    }
