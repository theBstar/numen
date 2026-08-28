"""AI-powered PR-to-task link suggestion engine."""

from __future__ import annotations

import json
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import list_edges, list_entities
from src.llm.client import call_llm
from src.llm.prompts import build_pr_task_link_prompt
from src.shared.models import Entity, LinkSuggestion
from src.shared.types import EdgeType, EntityType, LinkSuggestionStatus, TaskStatus

logger = logging.getLogger(__name__)

# Max PRs to process in a single Claude call
_BATCH_SIZE = 5


async def suggest_pr_task_links(
    db: AsyncSession,
    org_id: UUID,
    pr_entity_ids: list[UUID] | None = None,
) -> list[LinkSuggestion]:
    """Scan PRs for potential task links using Claude.

    If pr_entity_ids is provided, only check those PRs.
    Otherwise, scan all unlinked PRs in the org.

    Returns list of newly created LinkSuggestion records.
    """
    # 1. Find PR entities to scan
    prs = await _get_unlinked_prs(db, org_id, pr_entity_ids)
    if not prs:
        return []

    # 2. Find open tasks to match against
    tasks = await _get_open_tasks(db, org_id)
    if not tasks:
        logger.debug("No open tasks in org %s - skipping PR-task linking", org_id)
        return []

    # 3. Get existing suggestion pairs to avoid duplicates
    existing_pairs = await _get_existing_suggestion_pairs(db, org_id)

    # 4. Format data for Claude
    pr_dicts = _format_prs(prs)
    task_dicts = _format_tasks(tasks)

    # Build entity ID lookup maps
    pr_map = {str(pr.id): pr for pr in prs}
    task_map = {str(t.id): t for t in tasks}

    # 5. Process in batches
    new_suggestions: list[LinkSuggestion] = []

    for i in range(0, len(pr_dicts), _BATCH_SIZE):
        batch = pr_dicts[i : i + _BATCH_SIZE]
        try:
            matches = await _call_llm_for_matches(batch, task_dicts)
        except Exception as exc:
            logger.warning("Claude link suggestion call failed: %s", exc)
            continue

        for match in matches:
            pr_id = match.get("pr_id", "")
            task_id = match.get("task_id", "")
            confidence = match.get("confidence", 0.0)
            reasoning = match.get("reasoning", "")

            if pr_id not in pr_map or task_id not in task_map:
                continue
            if confidence < 0.4:
                continue

            pair = (pr_map[pr_id].id, task_map[task_id].id)
            if pair in existing_pairs:
                continue

            suggestion = LinkSuggestion(
                org_id=org_id,
                source_entity_id=pr_map[pr_id].id,
                target_entity_id=task_map[task_id].id,
                edge_type=EdgeType.SHIPS_TO,
                confidence=confidence,
                reasoning=reasoning,
                status="pending",
            )

            try:
                db.add(suggestion)
                await db.flush()
                new_suggestions.append(suggestion)
                existing_pairs.add(pair)
            except IntegrityError:
                await db.rollback()
                logger.debug("Suggestion already exists: PR %s -> Task %s", pr_id, task_id)

    if new_suggestions:
        logger.info(
            "Created %d AI link suggestion(s) for org %s",
            len(new_suggestions),
            org_id,
        )

    return new_suggestions


async def _get_unlinked_prs(db: AsyncSession, org_id: UUID, pr_ids: list[UUID] | None) -> list[Entity]:
    """Get PR entities that don't already have SHIPS_TO edges to tasks."""
    all_prs = await list_entities(db, org_id, entity_type=EntityType.COMMIT_PR, limit=1000)
    if pr_ids:
        pr_id_set = set(pr_ids)
        all_prs = [pr for pr in all_prs if pr.id in pr_id_set]

    if not all_prs:
        return []

    # Find PRs that already have SHIPS_TO edges to tasks
    linked_pr_ids: set[UUID] = set()
    for pr in all_prs:
        edges = await list_edges(
            db, entity_id=pr.id, edge_type=EdgeType.SHIPS_TO, direction="outgoing"
        )
        if edges:
            linked_pr_ids.add(pr.id)

    return [pr for pr in all_prs if pr.id not in linked_pr_ids]


async def _get_open_tasks(db: AsyncSession, org_id: UUID) -> list[Entity]:
    """Get non-done tasks in the org."""
    tasks = await list_entities(db, org_id, entity_type=EntityType.TASK, limit=1000)
    # Filter out done tasks
    return [t for t in tasks if (t.properties or {}).get("status") != TaskStatus.DONE]


async def _get_existing_suggestion_pairs(db: AsyncSession, org_id: UUID) -> set[tuple[UUID, UUID]]:
    """Get existing suggestion pairs to avoid duplicates."""
    result = await db.execute(
        select(
            LinkSuggestion.source_entity_id,
            LinkSuggestion.target_entity_id,
        ).where(
            LinkSuggestion.org_id == org_id,
            LinkSuggestion.status.in_(
                [LinkSuggestionStatus.PENDING, LinkSuggestionStatus.ACCEPTED]
            ),
        )
    )
    return {(row[0], row[1]) for row in result.all()}


def _format_prs(prs: list[Entity]) -> list[dict]:
    """Format PR entities for the Claude prompt."""
    result = []
    for pr in prs:
        props = pr.properties or {}
        result.append(
            {
                "id": str(pr.id),
                "title": pr.canonical_name,
                "description": props.get("body", ""),
                "branch": props.get("head_branch", ""),
                "author": props.get("author", ""),
                "reviewers": props.get("requested_reviewers", []) or [],
                "commit_messages": props.get("commit_messages", []) or [],
            }
        )
    return result


def _format_tasks(tasks: list[Entity]) -> list[dict]:
    """Format task entities for the Claude prompt."""
    result = []
    for task in tasks:
        props = task.properties or {}
        result.append(
            {
                "id": str(task.id),
                "title": task.canonical_name,
                "description": props.get("description", ""),
                "labels": props.get("labels", []),
                "project": props.get("project_name", ""),
                "assignee": props.get("assignee_name", ""),
            }
        )
    return result


async def _call_llm_for_matches(prs: list[dict], tasks: list[dict]) -> list[dict]:
    """Call Claude to match PRs to tasks. Returns parsed JSON matches."""
    system_prompt, user_prompt = build_pr_task_link_prompt(prs, tasks)

    response_text = await call_llm(
        system=system_prompt,
        user=user_prompt,
        max_tokens=1024,
    )

    # Parse JSON response - Claude should return a JSON array
    text = response_text.strip()
    # Strip markdown code fence if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        matches = json.loads(text)
        if not isinstance(matches, list):
            logger.warning("Claude returned non-array response: %s", text[:200])
            return []
        return matches
    except json.JSONDecodeError:
        logger.warning("Failed to parse Claude response as JSON: %s", text[:200])
        return []
