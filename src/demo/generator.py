"""Daily variance generator for demo data.

Adds realistic day-to-day changes to the demo org so the data feels alive.
Uses seeded random for reproducibility - the same date always produces the
same changes.
"""

from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.demo.fixtures import (
    NAMESPACE,
    PERSON_BY_KEY,
    PERSON_IDS,
)
from src.graph import (
    count_entities,
    get_edge_by_triple,
    list_edges,
    list_entities,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    Priority,
    PRState,
    SourceType,
    TaskStatus,
)

logger = logging.getLogger(__name__)

# ── Task name templates ──────────────────────────────────────────────────

_COMPONENTS = [
    "auth",
    "dashboard",
    "API",
    "graph",
    "webhook",
    "cache",
    "database",
    "notification",
    "search",
    "onboarding",
    "settings",
    "briefing",
    "connector",
    "scheduler",
    "email",
    "export",
]

_ISSUE_TYPES = [
    "timeout on large payloads",
    "validation error for edge cases",
    "memory leak under sustained load",
    "race condition in concurrent writes",
    "incorrect error message format",
    "missing pagination headers",
    "slow query on filtered results",
    "broken layout on small screens",
]

_FEATURE_ACTIONS = [
    "Add",
    "Implement",
    "Build",
    "Create",
    "Enable",
    "Integrate",
]

_FEATURE_TARGETS = [
    "bulk import endpoint",
    "team activity feed",
    "inline entity editing",
    "filter persistence in URL",
    "multi-select for batch actions",
    "drag-and-drop reordering",
    "real-time status indicator",
    "auto-refresh on data changes",
    "breadcrumb navigation",
    "context menu for quick actions",
    "progress bar for long operations",
    "copy-to-clipboard for entity IDs",
]

_STATUS_PROGRESSION = {
    TaskStatus.TODO: TaskStatus.IN_PROGRESS,
    TaskStatus.IN_PROGRESS: TaskStatus.IN_REVIEW,
    TaskStatus.IN_REVIEW: TaskStatus.DONE,
}

_PRIORITIES = [Priority.URGENT, Priority.HIGH, Priority.MEDIUM, Priority.LOW]
_PERSON_KEYS = list(PERSON_BY_KEY.keys())

_DECISION_TYPES = [
    "bug_filed",
    "pr_reviewed",
    "spec_written",
    "goal_updated",
    "item_dismissed",
    "capacity_allocated",
]

_DECISION_TRIGGERS = [
    "Monitoring alert detected anomaly",
    "Sprint retrospective action item",
    "Customer escalation via support",
    "Code review finding",
    "Weekly metrics review",
    "Team standup discussion",
    "Quarterly planning session",
    "On-call incident follow-up",
]

_DECISION_OUTCOMES = [
    "Filed new task and assigned to owner",
    "Approved with minor revisions requested",
    "Spec drafted and shared for review",
    "Progress updated based on recent data",
    "Deprioritized in favor of higher-impact work",
    "Reallocated team capacity for next sprint",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _variance_id(reference_date: date, suffix: str) -> uuid.UUID:
    """Deterministic UUID for variance items based on date + suffix."""
    return uuid.uuid5(NAMESPACE, f"variance-{reference_date.isoformat()}-{suffix}")


async def generate_daily_variance(
    db: AsyncSession,
    org_id: uuid.UUID,
    reference_date: date | None = None,
) -> dict:
    """Add daily variance to demo data.

    Uses seeded random for reproducibility - the same date always produces
    the same set of changes.

    Returns a summary dict of what was changed.
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc).date()

    rng = random.Random(reference_date.toordinal())
    summary = {
        "date": reference_date.isoformat(),
        "tasks_created": 0,
        "tasks_progressed": 0,
        "prs_created": 0,
        "prs_merged": 0,
        "deploys_created": 0,
        "goals_updated": 0,
        "decisions_created": 0,
        "edges_created": 0,
        "edges_updated": 0,
    }

    # 1. Create 2-4 new tasks
    num_new_tasks = rng.randint(2, 4)
    await _create_new_tasks(db, org_id, rng, reference_date, num_new_tasks, summary)

    # 2. Move 3-5 existing tasks to next status
    num_progress = rng.randint(3, 5)
    await _progress_tasks(db, org_id, rng, num_progress, summary)

    # 3. Create 1-2 new PRs linked to in_progress tasks
    num_new_prs = rng.randint(1, 2)
    await _create_new_prs(db, org_id, rng, reference_date, num_new_prs, summary)

    # 4. Merge 1-2 open PRs, create corresponding deploys
    num_merges = rng.randint(1, 2)
    await _merge_prs_and_deploy(db, org_id, rng, reference_date, num_merges, summary)

    # 5. Update goal progress slightly
    await _update_goal_progress(db, org_id, rng, summary)

    # 6. Create 1-2 new decisions
    num_decisions = rng.randint(1, 2)
    await _create_decisions(db, org_id, rng, reference_date, num_decisions, summary)

    # 7. Create 1-2 new BLOCKS edges between random tasks
    num_blocks = rng.randint(1, 2)
    await _create_block_edges(db, org_id, rng, reference_date, num_blocks, summary)

    # 8. Update edge last_active_at timestamps
    await _refresh_edge_timestamps(db, org_id, rng, summary)

    await db.flush()

    logger.info(
        "Daily variance applied for %s: %d tasks created, %d progressed, "
        "%d PRs created, %d merged, %d decisions, %d edges",
        reference_date.isoformat(),
        summary["tasks_created"],
        summary["tasks_progressed"],
        summary["prs_created"],
        summary["prs_merged"],
        summary["decisions_created"],
        summary["edges_created"],
    )

    return summary


# ── Variance operations ──────────────────────────────────────────────────


async def _create_new_tasks(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    ref_date: date,
    count: int,
    summary: dict,
) -> None:
    """Create new tasks with realistic names."""
    # Get current max task number
    existing_count = await count_entities(db, org_id, entity_type=EntityType.TASK)
    base_num = 4560 + existing_count + 1

    for i in range(count):
        task_num = base_num + i
        _variance_id(ref_date, f"task-{i}")

        # Generate task name
        if rng.random() < 0.4:
            # Bug fix
            component = rng.choice(_COMPONENTS)
            issue = rng.choice(_ISSUE_TYPES)
            title = f"Fix {component} {issue}"
        else:
            # Feature
            action = rng.choice(_FEATURE_ACTIONS)
            target = rng.choice(_FEATURE_TARGETS)
            title = f"{action} {target}"

        assignee_key = rng.choice(_PERSON_KEYS)
        assignee_data = PERSON_BY_KEY[assignee_key]
        priority = rng.choice(_PRIORITIES)
        status = rng.choices(["todo", "in_progress"], weights=[0.6, 0.4])[0]

        task_entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.TASK,
                source=SourceType.LINEAR,
                source_ids={"linear": f"ENG-{task_num}"},
                canonical_name=title,
                properties={
                    "title": title,
                    "identifier": f"ENG-{task_num}",
                    "status": status,
                    "priority": priority,
                    "assignee_email": assignee_data["email"],
                    "assignee_name": assignee_data["name"],
                    "labels": rng.sample(
                        ["frontend", "backend", "api", "bug", "feature", "performance", "ux"],
                        k=rng.randint(1, 3),
                    ),
                    "in_sprint": rng.random() < 0.3,
                    "url": f"https://linear.app/demo/issue/ENG-{task_num}",
                },
            ),
        )

        # Create OWNS/ASSIGNED_TO edges
        if assignee_key in PERSON_IDS:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=PERSON_IDS[assignee_key],
                    to_entity_id=task_entity.id,
                    type=EdgeType.OWNS,
                    evidence=[{"source": "demo-variance"}],
                ),
            )
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=PERSON_IDS[assignee_key],
                    to_entity_id=task_entity.id,
                    type=EdgeType.ASSIGNED_TO,
                    evidence=[{"source": "demo-variance"}],
                ),
            )
            summary["edges_created"] += 2

        summary["tasks_created"] += 1

    await db.flush()


async def _progress_tasks(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    count: int,
    summary: dict,
) -> None:
    """Move some tasks to their next status."""
    tasks = await list_entities(db, org_id, entity_type=EntityType.TASK, limit=1000)

    progressable = [t for t in tasks if (t.properties or {}).get("status") in _STATUS_PROGRESSION]

    if not progressable:
        return

    selected = rng.sample(progressable, min(count, len(progressable)))
    for task in selected:
        props = dict(task.properties or {})
        old_status = props.get("status", "todo")
        new_status = _STATUS_PROGRESSION.get(old_status)
        if new_status:
            await update_entity(db, task.id, properties={"status": new_status}, merge_properties=True)
            summary["tasks_progressed"] += 1


async def _create_new_prs(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    ref_date: date,
    count: int,
    summary: dict,
) -> None:
    """Create new PRs linked to in_progress tasks."""
    tasks = await list_entities(db, org_id, entity_type=EntityType.TASK, limit=1000)
    in_progress = [t for t in tasks if (t.properties or {}).get("status") == TaskStatus.IN_PROGRESS]

    if not in_progress:
        return

    selected = rng.sample(in_progress, min(count, len(in_progress)))
    for i, task in enumerate(selected):
        pr_num = 310 + ref_date.toordinal() % 1000 + i
        props = task.properties or {}
        assignee_email = props.get("assignee_email", "alice@demo.numen.team")

        # Find the person key from email
        author_key = "alice"
        for key, data in PERSON_BY_KEY.items():
            if data["email"] == assignee_email:
                author_key = key
                break

        branch = f"feat/{props.get('identifier', 'eng-unknown').lower()}"
        pr_entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.COMMIT_PR,
                source=SourceType.GITHUB,
                source_ids={"github": str(pr_num)},
                canonical_name=props.get("title", task.canonical_name),
                properties={
                    "title": props.get("title", task.canonical_name),
                    "number": pr_num,
                    "state": PRState.OPEN,
                    "branch": branch,
                    "author_email": assignee_email,
                    "author_name": PERSON_BY_KEY.get(author_key, {}).get("name", "Unknown"),
                    "additions": rng.randint(20, 500),
                    "deletions": rng.randint(5, 100),
                    "linked_task": props.get("identifier"),
                    "url": f"https://github.com/numen-team/numen/pull/{pr_num}",
                },
            ),
        )

        # AUTHORED edge
        if author_key in PERSON_IDS:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=PERSON_IDS[author_key],
                    to_entity_id=pr_entity.id,
                    type=EdgeType.AUTHORED,
                    evidence=[{"source": "demo-variance"}],
                ),
            )
            summary["edges_created"] += 1

        summary["prs_created"] += 1

    await db.flush()


async def _merge_prs_and_deploy(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    ref_date: date,
    count: int,
    summary: dict,
) -> None:
    """Merge some open PRs and create corresponding deploys."""
    prs = await list_entities(db, org_id, entity_type=EntityType.COMMIT_PR, limit=1000)
    open_prs = [p for p in prs if (p.properties or {}).get("state") == PRState.OPEN]

    if not open_prs:
        return

    selected = rng.sample(open_prs, min(count, len(open_prs)))
    for i, pr in enumerate(selected):
        # Merge the PR
        await update_entity(db, pr.id, properties={"state": PRState.MERGED}, merge_properties=True)
        summary["prs_merged"] += 1

        # Create a deploy
        props = pr.properties or {}
        env = rng.choice(["production", "staging"])
        deploy_entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DEPLOY,
                source=SourceType.GITHUB,
                source_ids={"github": f"deploy-var-{ref_date.isoformat()}-{i}"},
                canonical_name=f"Deploy to {env} - {props.get('title', 'unknown')}",
                properties={
                    "environment": env,
                    "status": "success",
                    "sha": props.get("sha", "unknown"),
                    "duration_seconds": rng.randint(60, 300),
                    "pr_number": props.get("number"),
                },
            ),
        )
        summary["deploys_created"] += 1

        # SHIPS_TO edge: PR -> deploy
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=pr.id,
                to_entity_id=deploy_entity.id,
                type=EdgeType.SHIPS_TO,
                evidence=[{"source": "demo-variance"}],
            ),
        )
        summary["edges_created"] += 1

    await db.flush()


async def _update_goal_progress(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    summary: dict,
) -> None:
    """Slightly update goal progress values."""
    goals = await list_entities(db, org_id, entity_type=EntityType.GOAL, limit=500)

    # Update 2-4 goals
    if not goals:
        return

    selected = rng.sample(goals, min(rng.randint(2, 4), len(goals)))
    for goal in selected:
        props = dict(goal.properties or {})
        current = props.get("current_value", 0)
        target = props.get("target_value", 100)

        if current < target:
            # Bump by 0.5-3.0
            increment = round(rng.uniform(0.5, 3.0), 1)
            new_value = min(current + increment, target)
            props["current_value"] = new_value

            # Also bump key results
            key_results = props.get("key_results", [])
            for kr in key_results:
                kr_current = kr.get("current", 0)
                kr_target = kr.get("target", 100)
                if kr_current < kr_target:
                    kr_increment = round(rng.uniform(0.5, 5.0), 1)
                    kr["current"] = min(kr_current + kr_increment, kr_target)

            props["key_results"] = key_results
            await update_entity(db, goal.id, properties=props)
            summary["goals_updated"] += 1


async def _create_decisions(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    ref_date: date,
    count: int,
    summary: dict,
) -> None:
    """Create new decision entities."""
    for i in range(count):
        _variance_id(ref_date, f"decision-{i}")
        dec_type = rng.choice(_DECISION_TYPES)
        actor_key = rng.choice(_PERSON_KEYS)
        actor_data = PERSON_BY_KEY[actor_key]

        title_prefix = {
            "bug_filed": "Bug reported:",
            "pr_reviewed": "PR review completed:",
            "spec_written": "Specification drafted:",
            "goal_updated": "Goal progress updated:",
            "item_dismissed": "Work item deprioritized:",
            "capacity_allocated": "Team capacity adjusted:",
        }

        component = rng.choice(_COMPONENTS)
        title = f"{title_prefix.get(dec_type, 'Decision:')} {component}"

        await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DECISION,
                source=SourceType.MANUAL,
                source_ids={"manual": f"dec-var-{ref_date.isoformat()}-{i}"},
                canonical_name=title,
                properties={
                    "type": dec_type,
                    "actor_email": actor_data["email"],
                    "actor_name": actor_data["name"],
                    "trigger": rng.choice(_DECISION_TRIGGERS),
                    "outcome": rng.choice(_DECISION_OUTCOMES),
                },
            ),
        )
        summary["decisions_created"] += 1

    await db.flush()


async def _create_block_edges(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    ref_date: date,
    count: int,
    summary: dict,
) -> None:
    """Create new BLOCKS edges between random in-flight tasks."""
    tasks = await list_entities(db, org_id, entity_type=EntityType.TASK, limit=1000)

    in_flight = [t for t in tasks if (t.properties or {}).get("status") in ("in_progress", "in_review")]

    if len(in_flight) < 2:
        return

    for i in range(min(count, len(in_flight) // 2)):
        pair = rng.sample(in_flight, 2)

        # Check if edge already exists
        existing = await get_edge_by_triple(db, pair[0].id, pair[1].id, EdgeType.BLOCKS)
        if existing is not None:
            continue

        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=pair[0].id,
                to_entity_id=pair[1].id,
                type=EdgeType.BLOCKS,
                weight=1.0,
                confidence=0.8,
                evidence=[{"source": "demo-variance", "reason": "Identified in standup"}],
            ),
        )
        summary["edges_created"] += 1

    await db.flush()


async def _refresh_edge_timestamps(
    db: AsyncSession,
    org_id: uuid.UUID,
    rng: random.Random,
    summary: dict,
) -> None:
    """Update last_active_at on a random subset of edges to simulate activity."""
    edges = await list_edges(db, org_id=org_id)

    if not edges:
        return

    # Limit to 200 for performance
    edges = edges[:200]

    # Update 10-20% of edges
    count = max(1, len(edges) // rng.randint(5, 10))
    selected = rng.sample(edges, min(count, len(edges)))

    for edge in selected:
        edge.last_active_at = _utcnow()
        summary["edges_updated"] += 1
