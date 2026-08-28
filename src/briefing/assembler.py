"""Per-person signal gathering for daily briefings.

Assembles BriefingItems tailored to each member's role by querying the
context graph, urgency scores, and entity relationships.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import (
    compute_goal_progress,
    count_edges,
    get_cross_team_blocking,
    get_entities_via_edge,
    get_entity,
    get_goal_coverage,
    get_stalled_prs,
    get_team_members,
    get_team_workload_summary,
    get_unowned_goals,
    list_edges,
)
from src.inference.scorer import get_top_urgent
from src.shared.models import Entity, OrgMember
from src.shared.provenance import (
    GraphTrace,
    RecommendationTrace,
    SourceTrace,
)
from src.shared.types import (
    BriefingItem,
    EdgeType,
    EntityType,
    PRState,
    RoleType,
    TaskStatus,
    UrgencyScore,
)

logger = logging.getLogger(__name__)

# How far back to look for recent activity (incidents, decisions, etc.)
_RECENT_WINDOW = timedelta(days=7)

# Adoption-rate threshold below which a feature is considered low-adoption
_LOW_ADOPTION_THRESHOLD = 0.20

# Maximum items returned per briefing
_MAX_BRIEFING_ITEMS = 10


# ── Helpers ──────────────────────────────────────────────────────────────


async def _get_person_entity(
    db: AsyncSession,
    member: OrgMember,
    org_id: UUID,
) -> Entity | None:
    """Look up the Person entity linked to this org member via person_entity_id."""
    if member.person_entity_id is None:
        return None

    entity = await get_entity(db, member.person_entity_id, org_id=org_id)
    if entity is not None and entity.type == EntityType.PERSON:
        return entity
    return None


async def _get_goal_tags_for_entity(
    db: AsyncSession,
    entity_id: UUID,
    org_id: UUID,
) -> list[str]:
    """Return goal names for an entity via TAGGED_TO edges."""
    goals = await get_entities_via_edge(
        db,
        entity_id,
        EdgeType.TAGGED_TO,
        direction="outgoing",
        target_type=EntityType.GOAL,
        org_id=org_id,
    )
    return [g.canonical_name for g in goals]


def _build_source_trace(entity: Entity) -> SourceTrace:
    """Build a SourceTrace from an entity's source metadata."""
    props = entity.properties or {}
    source_ids = entity.source_ids or {}

    # Determine source URL from properties or source_ids
    source_url = None
    for key in ("html_url", "url", "web_url", "link"):
        if key in props and isinstance(props[key], str) and props[key].startswith("http"):
            source_url = props[key]
            break

    if source_url is None:
        for sid in source_ids.values():
            if isinstance(sid, str) and sid.startswith("http"):
                source_url = sid
                break

    raw_source = entity.source
    source_str = raw_source.value if hasattr(raw_source, "value") else str(raw_source) if raw_source else "unknown"

    return SourceTrace(
        source=source_str,
        entity_id=str(entity.id),
        entity_name=entity.canonical_name,
        source_url=source_url,
        fetched_at=str(entity.updated_at) if entity.updated_at else None,
        fields_used=list(props.keys())[:10],
    )


_ENTITY_TYPE_ROUTES = {
    EntityType.TASK: "/tasks",
    EntityType.GOAL: "/goals",
    EntityType.PROJECT: "/projects",
}


async def _get_source_links(
    db: AsyncSession,
    entity_id: UUID,
    org_id: UUID,
) -> list[dict]:
    """Extract source links from an entity's properties + add internal app links."""
    entity = await get_entity(db, entity_id, org_id=org_id)
    if entity is None:
        return []

    props = entity.properties or {}
    source_ids = entity.source_ids or {}
    links: list[dict] = []

    # Internal app link (always first)
    route_prefix = _ENTITY_TYPE_ROUTES.get(entity.type, "/entities")
    links.append(
        {
            "source": "numen",
            "label": entity.canonical_name[:60],
            "url": f"{route_prefix}/{entity.id}",
        }
    )

    # External URLs from properties
    for key in ("html_url", "url", "web_url", "link", "slack_link", "page_url", "file_url"):
        if key in props and props[key] and isinstance(props[key], str) and props[key].startswith("http"):
            raw_src = entity.source
            source = raw_src.value if hasattr(raw_src, "value") else str(raw_src) if raw_src else "external"
            links.append({"source": source, "label": props.get("identifier", key), "url": props[key]})

    # Source ID URLs
    for source, sid in source_ids.items():
        if isinstance(sid, str) and sid.startswith("http"):
            links.append({"source": source, "label": source, "url": sid})

    return links


def _score_to_briefing_item(
    score: UrgencyScore,
    entity: Entity,
    why: str,
    goal_tags: list[str],
    source_links: list[dict],
    suggested_action: str | None = None,
) -> BriefingItem:
    """Convert an UrgencyScore + entity into a BriefingItem."""
    # Build a full RecommendationTrace wrapping scoring provenance + source info
    source_trace = _build_source_trace(entity)
    trace = RecommendationTrace(
        recommendation_id=str(score.entity_id),
        generated_at=str(score.computed_at),
        source_traces=[source_trace],
        scoring_traces=score.provenance,
    )

    return BriefingItem(
        entity_id=score.entity_id,
        entity_type=entity.type,
        title=entity.canonical_name,
        why_it_matters=why,
        urgency_score=score.score,
        goal_tags=goal_tags,
        source_links=source_links,
        suggested_action=suggested_action,
        provenance=[trace.model_dump()],
    )


# ── Engineer briefing ────────────────────────────────────────────────────


async def _assemble_engineer_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to an engineer."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. Top urgent owned tasks
    urgent_scores = await get_top_urgent(db, org_id, person_id, role=RoleType.ENGINEER, limit=5)
    for score in urgent_scores:
        entity = await get_entity(db, score.entity_id, org_id=org_id)
        if entity is None:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, score.entity_id, org_id)
        source_links = await _get_source_links(db, score.entity_id, org_id)

        components = score.components or {}
        why_parts: list[str] = []
        if components.get("deadline_proximity", 0) > 0.5:
            why_parts.append("approaching deadline")
        if components.get("blocking_count", 0) > 0:
            why_parts.append(f"blocking {int(components['blocking_count'])} other item(s)")
        if components.get("goal_alignment", 0) > 0.5:
            why_parts.append("aligned with top team goals")
        why = "; ".join(why_parts) if why_parts else "High urgency based on combined signals"

        items.append(
            _score_to_briefing_item(
                score=score,
                entity=entity,
                why=why,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review and move forward today",
            )
        )

    # 2. PRs awaiting review (COMMIT_PR entities where member is mentioned, status=open)
    mentioned_entities = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.MENTIONED_IN,
        direction="incoming",
        target_type=EntityType.COMMIT_PR,
        org_id=org_id,
    )
    prs = [pr for pr in mentioned_entities if (pr.properties or {}).get("status") == PRState.OPEN][:5]
    for pr in prs:
        goal_tags = await _get_goal_tags_for_entity(db, pr.id, org_id)
        source_links = await _get_source_links(db, pr.id, org_id)
        props = pr.properties or {}
        author = props.get("author", "a teammate")

        pr_trace = RecommendationTrace(
            recommendation_id=str(pr.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(pr)],
            graph_traces=[
                GraphTrace(
                    traversal_type="review_assignment",
                    path=[
                        {
                            "entity_id": str(pr.id),
                            "entity_name": pr.canonical_name,
                            "edge_type": "mentioned_in",
                            "direction": "to_person",
                        },
                    ],
                    depth=1,
                    entities_visited=2,
                    description=f"{pr.canonical_name} - review requested by {author}",
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=pr.id,
                entity_type=EntityType.COMMIT_PR,
                title=f"PR Review: {pr.canonical_name}",
                why_it_matters=f"{author} requested your review on this pull request",
                urgency_score=0.7,  # Default moderate urgency for review requests
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review and provide feedback",
                provenance=[pr_trace.model_dump()],
            )
        )

    # 3. Blocking chains (tasks that this person's work blocks for others)
    owned_tasks = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.OWNS,
        direction="outgoing",
        target_type=EntityType.TASK,
        org_id=org_id,
    )
    owned_task_ids = [t.id for t in owned_tasks]

    for task_id in owned_task_ids[:5]:
        # Check if this task blocks others
        blocked_count = await count_edges(db, task_id, EdgeType.BLOCKS, direction="outgoing", org_id=org_id)
        if blocked_count == 0:
            continue

        entity = await get_entity(db, task_id, org_id=org_id)
        if entity is None:
            continue

        # Skip if already in items from urgent scores
        if any(item.entity_id == task_id for item in items):
            continue

        goal_tags = await _get_goal_tags_for_entity(db, task_id, org_id)
        source_links = await _get_source_links(db, task_id, org_id)

        blocker_trace = RecommendationTrace(
            recommendation_id=str(task_id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(entity)],
            graph_traces=[
                GraphTrace(
                    traversal_type="blocking_chain",
                    path=[
                        {
                            "entity_id": str(entity.id),
                            "entity_name": entity.canonical_name,
                            "edge_type": "blocks",
                        }
                    ],
                    depth=1,
                    entities_visited=blocked_count + 1,
                    description=f"{entity.canonical_name} blocks {blocked_count} downstream task(s)",
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=task_id,
                entity_type=EntityType.TASK,
                title=f"Blocker: {entity.canonical_name}",
                why_it_matters=f"Your work on this is blocking {blocked_count} other task(s)",
                urgency_score=0.8,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Unblock downstream work",
                provenance=[blocker_trace.model_dump()],
            )
        )

    # 4. Recent incidents on services this person has committed to
    recent_cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    # Get entities connected via OWNS, MENTIONED_IN, AUTHORED edges from this person
    incident_candidates: list[Entity] = []
    for edge_type in [EdgeType.OWNS, EdgeType.MENTIONED_IN, EdgeType.AUTHORED]:
        connected = await get_entities_via_edge(
            db,
            person_id,
            edge_type,
            direction="outgoing",
            target_type=EntityType.INCIDENT,
            org_id=org_id,
        )
        incident_candidates.extend(connected)
    # Deduplicate and filter by recency
    seen_ids: set[UUID] = set()
    incidents: list[Entity] = []
    for inc in incident_candidates:
        if inc.id not in seen_ids and inc.org_id == org_id and inc.created_at >= recent_cutoff:
            seen_ids.add(inc.id)
            incidents.append(inc)
            if len(incidents) >= 3:
                break
    for incident in incidents:
        if any(item.entity_id == incident.id for item in items):
            continue

        goal_tags = await _get_goal_tags_for_entity(db, incident.id, org_id)
        source_links = await _get_source_links(db, incident.id, org_id)
        props = incident.properties or {}
        severity = props.get("severity", "unknown")

        incident_trace = RecommendationTrace(
            recommendation_id=str(incident.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(incident)],
            graph_traces=[
                GraphTrace(
                    traversal_type="ownership",
                    path=[
                        {
                            "entity_id": str(incident.id),
                            "entity_name": incident.canonical_name,
                            "edge_type": "owns/mentioned_in",
                        }
                    ],
                    depth=1,
                    entities_visited=1,
                    description=f"Severity {severity} incident linked to your services",
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=incident.id,
                entity_type=EntityType.INCIDENT,
                title=f"Incident: {incident.canonical_name}",
                why_it_matters=f"Severity {severity} incident on a service you contribute to",
                urgency_score=0.9 if severity in ("critical", "high") else 0.6,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Check incident status and assist if needed",
                provenance=[incident_trace.model_dump()],
            )
        )

    return items


# ── PM briefing ──────────────────────────────────────────────────────────


async def _assemble_pm_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to a product manager."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. Top urgent features via urgency scores
    urgent_scores = await get_top_urgent(db, org_id, person_id, role=RoleType.PM, limit=5)
    for score in urgent_scores:
        entity = await get_entity(db, score.entity_id, org_id=org_id)
        if entity is None:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, score.entity_id, org_id)
        source_links = await _get_source_links(db, score.entity_id, org_id)

        components = score.components or {}
        why_parts: list[str] = []
        if components.get("deadline_proximity", 0) > 0.5:
            why_parts.append("deadline approaching")
        if components.get("blocked_tasks", 0) > 0:
            why_parts.append(f"{int(components['blocked_tasks'])} blocked task(s) need attention")
        if components.get("stakeholder_interest", 0) > 0.5:
            why_parts.append("high stakeholder interest")
        why = "; ".join(why_parts) if why_parts else "High priority based on combined signals"

        items.append(
            _score_to_briefing_item(
                score=score,
                entity=entity,
                why=why,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review progress and unblock if needed",
            )
        )

    # 2. Blocked task counts per feature
    features = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.OWNS,
        direction="outgoing",
        target_type=EntityType.FEATURE,
        org_id=org_id,
    )

    for feature in features:
        if any(item.entity_id == feature.id for item in items):
            continue

        # Count tasks TAGGED_TO this feature that have BLOCKS edges
        tagged_tasks = await get_entities_via_edge(
            db,
            feature.id,
            EdgeType.TAGGED_TO,
            direction="incoming",
            target_type=EntityType.TASK,
            org_id=org_id,
        )
        blocked_count = 0
        for tagged_task in tagged_tasks:
            blocks_count = await count_edges(db, tagged_task.id, EdgeType.BLOCKS, direction="outgoing", org_id=org_id)
            if blocks_count > 0:
                blocked_count += 1
        if blocked_count == 0:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, feature.id, org_id)
        source_links = await _get_source_links(db, feature.id, org_id)

        feature_block_trace = RecommendationTrace(
            recommendation_id=str(feature.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(feature)],
            graph_traces=[
                GraphTrace(
                    traversal_type="blocking_chain",
                    path=[
                        {
                            "entity_id": str(feature.id),
                            "entity_name": feature.canonical_name,
                            "edge_type": "tagged_to",
                        }
                    ],
                    depth=2,
                    entities_visited=blocked_count + 1,
                    description=f"{blocked_count} task(s) under {feature.canonical_name} are blocked",
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=feature.id,
                entity_type=EntityType.FEATURE,
                title=f"Blocked work: {feature.canonical_name}",
                why_it_matters=f"{blocked_count} task(s) under this feature are blocked",
                urgency_score=0.75,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Investigate blockers and help resolve",
                provenance=[feature_block_trace.model_dump()],
            )
        )

    # 3. Open decisions (Decision entities with recent MENTIONED_IN for this person)
    recent_cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    mentioned_decisions = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.MENTIONED_IN,
        direction="incoming",
        target_type=EntityType.DECISION,
        org_id=org_id,
    )
    # Filter by org and recency of the edge
    decisions_filtered: list[Entity] = []
    for dec in mentioned_decisions:
        if dec.org_id != org_id:
            continue
        # Check if the MENTIONED_IN edge is recent
        edges = await list_edges(
            db,
            entity_id=dec.id,
            edge_type=EdgeType.MENTIONED_IN,
            direction="outgoing",
            org_id=org_id,
        )
        recent_edge = any(
            e.to_entity_id == person_id and e.last_active_at and e.last_active_at >= recent_cutoff for e in edges
        )
        if recent_edge:
            decisions_filtered.append(dec)
            if len(decisions_filtered) >= 5:
                break
    decisions = decisions_filtered
    for decision in decisions:
        if any(item.entity_id == decision.id for item in items):
            continue

        goal_tags = await _get_goal_tags_for_entity(db, decision.id, org_id)
        source_links = await _get_source_links(db, decision.id, org_id)
        props = decision.properties or {}
        status = props.get("status", "open")

        decision_trace = RecommendationTrace(
            recommendation_id=str(decision.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(decision)],
            graph_traces=[
                GraphTrace(
                    traversal_type="mention_scan",
                    path=[
                        {
                            "entity_id": str(decision.id),
                            "entity_name": decision.canonical_name,
                            "edge_type": "mentioned_in",
                        }
                    ],
                    depth=1,
                    entities_visited=1,
                    description=f"Decision ({status}) recently mentioned involving you",
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=decision.id,
                entity_type=EntityType.DECISION,
                title=f"Decision needed: {decision.canonical_name}",
                why_it_matters=f"This decision ({status}) was recently raised and involves you",
                urgency_score=0.7,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review context and provide your input",
                provenance=[decision_trace.model_dump()],
            )
        )

    # 4. Low-adoption features
    low_adoption_features = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.OWNS,
        direction="outgoing",
        target_type=EntityType.FEATURE,
        org_id=org_id,
    )
    for feature in low_adoption_features:
        if any(item.entity_id == feature.id for item in items):
            continue

        props = feature.properties or {}
        adoption_rate = props.get("adoption_rate")
        if adoption_rate is None or adoption_rate >= _LOW_ADOPTION_THRESHOLD:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, feature.id, org_id)
        source_links = await _get_source_links(db, feature.id, org_id)
        pct = round(adoption_rate * 100, 1)

        adoption_trace = RecommendationTrace(
            recommendation_id=str(feature.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(feature)],
            graph_traces=[
                GraphTrace(
                    traversal_type="ownership",
                    path=[
                        {
                            "entity_id": str(feature.id),
                            "entity_name": feature.canonical_name,
                            "edge_type": "owns",
                        }
                    ],
                    depth=1,
                    entities_visited=1,
                    description=f"{feature.canonical_name} has {pct}% adoption - below {_LOW_ADOPTION_THRESHOLD * 100}% threshold",  # noqa: E501
                )
            ],
        )

        items.append(
            BriefingItem(
                entity_id=feature.id,
                entity_type=EntityType.FEATURE,
                title=f"Low adoption: {feature.canonical_name}",
                why_it_matters=f"Only {pct}% adoption - may need attention or iteration",
                urgency_score=0.5,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Investigate adoption barriers and consider next steps",
                provenance=[adoption_trace.model_dump()],
            )
        )

    return items


# ── EM briefing ───────────────────────────────────────────────────────


async def _assemble_em_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to an engineering manager."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. IC Blockers - direct reports with blocked tasks
    team = await get_team_members(db, person_id)
    team_ids = [m.id for m in team]
    team_name_map = {m.id: m.canonical_name for m in team}

    for report in team:
        owned_tasks = await get_entities_via_edge(
            db,
            report.id,
            EdgeType.OWNS,
            direction="outgoing",
            target_type=EntityType.TASK,
            org_id=org_id,
        )
        for task in owned_tasks[:5]:
            blocked_count = await count_edges(db, task.id, EdgeType.BLOCKS, direction="incoming", org_id=org_id)
            if blocked_count == 0:
                continue
            if any(item.entity_id == task.id for item in items):
                continue

            goal_tags = await _get_goal_tags_for_entity(db, task.id, org_id)
            source_links = await _get_source_links(db, task.id, org_id)
            report_name = team_name_map.get(report.id, "a report")

            trace = RecommendationTrace(
                recommendation_id=str(task.id),
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[_build_source_trace(task)],
                graph_traces=[
                    GraphTrace(
                        traversal_type="ic_blocked",
                        path=[
                            {
                                "entity_id": str(task.id),
                                "entity_name": task.canonical_name,
                                "edge_type": "blocks",
                            }
                        ],
                        depth=2,
                        entities_visited=blocked_count + 1,
                        description=f"{report_name}'s task is blocked",
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=task.id,
                    entity_type=EntityType.TASK,
                    title=f"Blocked: {task.canonical_name}",
                    why_it_matters=f"{report_name} is blocked on this task",
                    urgency_score=0.8,
                    goal_tags=goal_tags,
                    source_links=source_links,
                    suggested_action=f"Help {report_name} unblock",
                    provenance=[trace.model_dump()],
                )
            )

    # 2. Stalled PRs from team
    if team_ids:
        stalled = await get_stalled_prs(db, org_id, team_ids, stale_hours=48)
        for pr in stalled[:5]:
            if any(item.entity_id == pr.id for item in items):
                continue
            goal_tags = await _get_goal_tags_for_entity(db, pr.id, org_id)
            source_links = await _get_source_links(db, pr.id, org_id)
            props = pr.properties or {}
            author = props.get("author", "a team member")

            trace = RecommendationTrace(
                recommendation_id=str(pr.id),
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[_build_source_trace(pr)],
                graph_traces=[
                    GraphTrace(
                        traversal_type="stalled_pr",
                        path=[
                            {
                                "entity_id": str(pr.id),
                                "entity_name": pr.canonical_name,
                                "edge_type": "authored",
                            }
                        ],
                        depth=1,
                        entities_visited=1,
                        description=f"PR by {author} has had no activity for 48+ hours",
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=pr.id,
                    entity_type=EntityType.COMMIT_PR,
                    title=f"Stalled PR: {pr.canonical_name}",
                    why_it_matters=f"Open >48h with no activity - authored by {author}",
                    urgency_score=0.65,
                    goal_tags=goal_tags,
                    source_links=source_links,
                    suggested_action="Check if review or action is needed",
                    provenance=[trace.model_dump()],
                )
            )

    # 3. 1:1 Prep - per-report summary as briefing items
    workload_summary = await get_team_workload_summary(db, person_id)
    for member_id_str, workload in workload_summary.get("members", {}).items():
        member_uuid = UUID(member_id_str)
        name = workload.get("name", "Report")
        in_progress = workload.get("in_progress", 0)
        workload.get("todo", 0)
        total = workload.get("total", 0)

        # 4. WIP Overload check (>5 in progress)
        if in_progress > 5:
            trace = RecommendationTrace(
                recommendation_id=member_id_str,
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[],
                graph_traces=[
                    GraphTrace(
                        traversal_type="wip_overload",
                        path=[{"entity_id": member_id_str, "entity_name": name, "edge_type": "owns"}],
                        depth=1,
                        entities_visited=in_progress,
                        description=f"{name} has {in_progress} tasks in progress",
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=member_uuid,
                    entity_type=EntityType.PERSON,
                    title=f"WIP overload: {name}",
                    why_it_matters=f"{name} has {in_progress} tasks in progress ({total} total) - may need help prioritizing",  # noqa: E501
                    urgency_score=0.7,
                    goal_tags=[],
                    source_links=[],
                    suggested_action=f"Discuss priorities in 1:1 with {name}",
                    provenance=[trace.model_dump()],
                )
            )

    return items


# ── Designer briefing ─────────────────────────────────────────────────


async def _assemble_designer_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to a designer."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. Urgent owned tasks (same pattern as engineer)
    urgent_scores = await get_top_urgent(db, org_id, person_id, role=RoleType.DESIGNER, limit=5)
    for score in urgent_scores:
        entity = await get_entity(db, score.entity_id, org_id=org_id)
        if entity is None:
            continue
        goal_tags = await _get_goal_tags_for_entity(db, score.entity_id, org_id)
        source_links = await _get_source_links(db, score.entity_id, org_id)
        components = score.components or {}
        why_parts: list[str] = []
        if components.get("deadline_proximity", 0) > 0.5:
            why_parts.append("approaching deadline")
        if components.get("blocking_count", 0) > 0:
            why_parts.append(f"blocking {int(components['blocking_count'])} other item(s)")
        why = "; ".join(why_parts) if why_parts else "High urgency based on combined signals"
        items.append(
            _score_to_briefing_item(
                score=score,
                entity=entity,
                why=why,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review and move forward today",
            )
        )

    # 2. Conflicting specs - entities connected via CONFLICTS_WITH
    owned_docs = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.OWNS,
        direction="outgoing",
        target_type=EntityType.DOCUMENT,
        org_id=org_id,
    )
    mentioned_docs = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.MENTIONED_IN,
        direction="incoming",
        target_type=EntityType.DOCUMENT,
        org_id=org_id,
    )
    all_doc_ids = {d.id for d in owned_docs + mentioned_docs}
    for doc in owned_docs + mentioned_docs:
        if doc.id not in all_doc_ids:
            continue
        all_doc_ids.discard(doc.id)  # process once

        conflict_edges = await list_edges(
            db, entity_id=doc.id, edge_type=EdgeType.CONFLICTS_WITH, direction="both", org_id=org_id
        )
        if not conflict_edges:
            continue
        if any(item.entity_id == doc.id for item in items):
            continue

        goal_tags = await _get_goal_tags_for_entity(db, doc.id, org_id)
        source_links = await _get_source_links(db, doc.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(doc.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(doc)],
            graph_traces=[
                GraphTrace(
                    traversal_type="conflicting_spec",
                    path=[
                        {
                            "entity_id": str(doc.id),
                            "entity_name": doc.canonical_name,
                            "edge_type": "conflicts_with",
                        }
                    ],
                    depth=1,
                    entities_visited=len(conflict_edges) + 1,
                    description=f"{doc.canonical_name} has {len(conflict_edges)} conflicting spec(s)",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=doc.id,
                entity_type=EntityType.DOCUMENT,
                title=f"Conflict: {doc.canonical_name}",
                why_it_matters=f"This spec conflicts with {len(conflict_edges)} other document(s)",
                urgency_score=0.7,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review conflicting specs and align",
                provenance=[trace.model_dump()],
            )
        )

    # 3. Overdue design reviews (PRs/docs where designer has REVIEWS edge, open >48h)
    review_targets = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.REVIEWS,
        direction="outgoing",
        org_id=org_id,
    )
    cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    for target in review_targets:
        if any(item.entity_id == target.id for item in items):
            continue
        props = target.properties or {}
        status = props.get("status", "")
        if status not in (PRState.OPEN, "open", "in_review"):
            continue
        if target.updated_at and target.updated_at >= (datetime.now(timezone.utc) - timedelta(hours=48)):
            continue  # Not stale yet

        goal_tags = await _get_goal_tags_for_entity(db, target.id, org_id)
        source_links = await _get_source_links(db, target.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(target.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(target)],
            graph_traces=[
                GraphTrace(
                    traversal_type="overdue_review",
                    path=[
                        {
                            "entity_id": str(target.id),
                            "entity_name": target.canonical_name,
                            "edge_type": "reviews",
                        }
                    ],
                    depth=1,
                    entities_visited=1,
                    description="Awaiting your review for 48+ hours",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=target.id,
                entity_type=target.type,
                title=f"Overdue review: {target.canonical_name}",
                why_it_matters="This has been waiting for your design review for over 48 hours",
                urgency_score=0.7,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Complete your review",
                provenance=[trace.model_dump()],
            )
        )

    # 4. Handoffs ready - tasks recently moved to done on features designer is linked to
    mentioned_features = await get_entities_via_edge(
        db,
        person_id,
        EdgeType.MENTIONED_IN,
        direction="incoming",
        target_type=EntityType.FEATURE,
        org_id=org_id,
    )
    for feature in mentioned_features[:5]:
        tagged_tasks = await get_entities_via_edge(
            db,
            feature.id,
            EdgeType.TAGGED_TO,
            direction="incoming",
            target_type=EntityType.TASK,
            org_id=org_id,
        )
        for task in tagged_tasks:
            if any(item.entity_id == task.id for item in items):
                continue
            props = task.properties or {}
            if props.get("status") != TaskStatus.DONE:
                continue
            if task.updated_at and task.updated_at < cutoff:
                continue  # Too old

            goal_tags = await _get_goal_tags_for_entity(db, task.id, org_id)
            source_links = await _get_source_links(db, task.id, org_id)
            trace = RecommendationTrace(
                recommendation_id=str(task.id),
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[_build_source_trace(task)],
                graph_traces=[
                    GraphTrace(
                        traversal_type="handoff_ready",
                        path=[
                            {
                                "entity_id": str(feature.id),
                                "entity_name": feature.canonical_name,
                                "edge_type": "tagged_to",
                            },
                            {
                                "entity_id": str(task.id),
                                "entity_name": task.canonical_name,
                                "edge_type": "status:done",
                            },
                        ],
                        depth=2,
                        entities_visited=2,
                        description=f"Engineering work on {task.canonical_name} is done - ready for design verification",  # noqa: E501
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=task.id,
                    entity_type=EntityType.TASK,
                    title=f"Handoff ready: {task.canonical_name}",
                    why_it_matters=f"Engineering completed this task under {feature.canonical_name} - ready for design review",  # noqa: E501
                    urgency_score=0.6,
                    goal_tags=goal_tags,
                    source_links=source_links,
                    suggested_action="Verify design implementation",
                    provenance=[trace.model_dump()],
                )
            )

    return items


# ── CTO briefing ──────────────────────────────────────────────────────


async def _assemble_cto_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to a CTO."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. Org bottlenecks - tasks with the most downstream BLOCKS edges
    from src.graph import list_entities as repo_list_entities

    all_tasks_result = await repo_list_entities(db, org_id=org_id, entity_type=EntityType.TASK, limit=200)
    task_block_counts: list[tuple[Entity, int]] = []
    for task in all_tasks_result:
        blocked_count = await count_edges(db, task.id, EdgeType.BLOCKS, direction="outgoing", org_id=org_id)
        if blocked_count > 0:
            task_block_counts.append((task, blocked_count))

    task_block_counts.sort(key=lambda x: x[1], reverse=True)
    for task, blocked_count in task_block_counts[:5]:
        if any(item.entity_id == task.id for item in items):
            continue
        goal_tags = await _get_goal_tags_for_entity(db, task.id, org_id)
        source_links = await _get_source_links(db, task.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(task.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(task)],
            graph_traces=[
                GraphTrace(
                    traversal_type="org_bottleneck",
                    path=[
                        {
                            "entity_id": str(task.id),
                            "entity_name": task.canonical_name,
                            "edge_type": "blocks",
                        }
                    ],
                    depth=1,
                    entities_visited=blocked_count + 1,
                    description=f"Blocking {blocked_count} downstream task(s) across the org",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=task.id,
                entity_type=EntityType.TASK,
                title=f"Bottleneck: {task.canonical_name}",
                why_it_matters=f"This task is blocking {blocked_count} other tasks across the org",
                urgency_score=min(0.6 + blocked_count * 0.1, 1.0),
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Escalate or reassign to unblock",
                provenance=[trace.model_dump()],
            )
        )

    # 2. At-risk goals - low progress with approaching deadline
    coverage = await get_goal_coverage(db, org_id)
    for goal_info in coverage:
        goal_id = goal_info["goal_id"]
        if any(item.entity_id == goal_id for item in items):
            continue

        progress = await compute_goal_progress(db, goal_id)
        computed = progress.get("computed_progress", 0)
        if computed >= 30:
            continue

        goal_entity = await get_entity(db, goal_id, org_id=org_id)
        if goal_entity is None:
            continue

        props = goal_entity.properties or {}
        end_date_str = props.get("time_bound_end")
        if end_date_str:
            try:
                end_date = datetime.fromisoformat(end_date_str)
                if end_date.tzinfo is None:
                    end_date = end_date.replace(tzinfo=timezone.utc)
                days_remaining = (end_date - datetime.now(timezone.utc)).days
                if days_remaining > 30:
                    continue
            except (ValueError, TypeError):
                pass

        goal_tags = [goal_entity.canonical_name]
        source_links = await _get_source_links(db, goal_id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(goal_id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(goal_entity)],
            graph_traces=[
                GraphTrace(
                    traversal_type="at_risk_goal",
                    path=[
                        {
                            "entity_id": str(goal_id),
                            "entity_name": goal_entity.canonical_name,
                            "edge_type": "tagged_to",
                        }
                    ],
                    depth=1,
                    entities_visited=1,
                    description=f"Goal at {computed}% progress with deadline approaching",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=goal_id,
                entity_type=EntityType.GOAL,
                title=f"At risk: {goal_entity.canonical_name}",
                why_it_matters=f"Only {computed}% progress - may miss deadline",
                urgency_score=0.85,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Review scope or reallocate resources",
                provenance=[trace.model_dump()],
            )
        )

    # 3. Cross-team blocking gaps
    team = await get_team_members(db, person_id)
    team_ids = [m.id for m in team]
    if team_ids:
        cross_blocks = await get_cross_team_blocking(db, org_id, team_ids)
        for cb in cross_blocks[:3]:
            blocker = cb.get("blocker_task")
            blocked = cb.get("blocked_task")
            if not blocker or not blocked:
                continue
            if any(item.entity_id == blocker.id for item in items):
                continue

            goal_tags = await _get_goal_tags_for_entity(db, blocker.id, org_id)
            source_links = await _get_source_links(db, blocker.id, org_id)
            trace = RecommendationTrace(
                recommendation_id=str(blocker.id),
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[_build_source_trace(blocker)],
                graph_traces=[
                    GraphTrace(
                        traversal_type="cross_team_gap",
                        path=[
                            {
                                "entity_id": str(blocker.id),
                                "entity_name": blocker.canonical_name,
                                "edge_type": "blocks",
                            },
                            {
                                "entity_id": str(blocked.id),
                                "entity_name": blocked.canonical_name,
                                "edge_type": "blocked",
                            },
                        ],
                        depth=2,
                        entities_visited=2,
                        description="Cross-team dependency: your team's task blocks another team",
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=blocker.id,
                    entity_type=EntityType.TASK,
                    title=f"Cross-team blocker: {blocker.canonical_name}",
                    why_it_matters=f"This blocks {blocked.canonical_name} on another team",
                    urgency_score=0.8,
                    goal_tags=goal_tags,
                    source_links=source_links,
                    suggested_action="Coordinate across teams to unblock",
                    provenance=[trace.model_dump()],
                )
            )

    # 4. Active incidents (org-wide, last 7 days)
    recent_cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    from src.graph import list_entities as _list

    all_incidents = await _list(db, org_id=org_id, entity_type=EntityType.INCIDENT, limit=50)
    recent_incidents = [i for i in all_incidents if i.created_at and i.created_at >= recent_cutoff]
    for incident in recent_incidents[:3]:
        if any(item.entity_id == incident.id for item in items):
            continue
        props = incident.properties or {}
        severity = props.get("severity", "unknown")
        goal_tags = await _get_goal_tags_for_entity(db, incident.id, org_id)
        source_links = await _get_source_links(db, incident.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(incident.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(incident)],
            graph_traces=[
                GraphTrace(
                    traversal_type="recent_incident",
                    path=[{"entity_id": str(incident.id), "entity_name": incident.canonical_name}],
                    depth=0,
                    entities_visited=1,
                    description=f"Severity {severity} incident in the last 7 days",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=incident.id,
                entity_type=EntityType.INCIDENT,
                title=f"Incident: {incident.canonical_name}",
                why_it_matters=f"Severity {severity} incident affecting the org",
                urgency_score=0.9 if severity in ("critical", "high") else 0.6,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Ensure appropriate response and follow-up",
                provenance=[trace.model_dump()],
            )
        )

    return items


# ── VP Engineering briefing ───────────────────────────────────────────


async def _assemble_vp_eng_briefing(db: AsyncSession, member: OrgMember, person_entity: Entity) -> list[BriefingItem]:
    """Gather signals relevant to a VP of Engineering."""
    items: list[BriefingItem] = []
    person_id = person_entity.id
    org_id = member.org_id

    # 1. Team health per EM - aggregate workloads for direct reports (EMs)
    direct_reports = await get_team_members(db, person_id)
    for report in direct_reports:
        summary = await get_team_workload_summary(db, report.id)
        totals = summary.get("team_totals", {})
        team_in_progress = totals.get(TaskStatus.IN_PROGRESS, 0)
        totals.get("total", 0)
        team_size = len(summary.get("members", {}))

        if team_size == 0:
            continue

        avg_wip = team_in_progress / team_size if team_size else 0
        if avg_wip <= 3:
            continue  # Healthy, skip

        trace = RecommendationTrace(
            recommendation_id=str(report.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[],
            graph_traces=[
                GraphTrace(
                    traversal_type="team_health",
                    path=[
                        {
                            "entity_id": str(report.id),
                            "entity_name": report.canonical_name,
                            "edge_type": "reports_to",
                        }
                    ],
                    depth=2,
                    entities_visited=team_size + 1,
                    description=f"{report.canonical_name}'s team: {team_in_progress} WIP across {team_size} ICs (avg {avg_wip:.1f})",  # noqa: E501
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=report.id,
                entity_type=EntityType.PERSON,
                title=f"High WIP: {report.canonical_name}'s team",
                why_it_matters=f"{team_in_progress} tasks in progress across {team_size} ICs (avg {avg_wip:.1f} per person)",  # noqa: E501
                urgency_score=min(0.5 + avg_wip * 0.05, 0.9),
                goal_tags=[],
                source_links=[],
                suggested_action=f"Discuss workload with {report.canonical_name}",
                provenance=[trace.model_dump()],
            )
        )

    # 2. Sprint state - org-wide task status distribution
    from src.graph import list_entities as _list_ents

    all_tasks = await _list_ents(db, org_id=org_id, entity_type=EntityType.TASK, limit=500)
    status_counts: dict[str, int] = {
        TaskStatus.TODO: 0,
        TaskStatus.IN_PROGRESS: 0,
        TaskStatus.IN_REVIEW: 0,
        TaskStatus.DONE: 0,
    }
    for t in all_tasks:
        s = (t.properties or {}).get("status", "").lower().replace(" ", "_")
        if s in status_counts:
            status_counts[s] += 1

    total = sum(status_counts.values())
    if total > 0:
        in_progress_pct = round(status_counts[TaskStatus.IN_PROGRESS] / total * 100)
        if in_progress_pct > 40:  # High WIP ratio
            trace = RecommendationTrace(
                recommendation_id="sprint_state",
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[],
                graph_traces=[
                    GraphTrace(
                        traversal_type="sprint_state",
                        path=[],
                        depth=0,
                        entities_visited=total,
                        description=f"Org sprint: {in_progress_pct}% in progress, {status_counts[TaskStatus.TODO]} todo, {status_counts[TaskStatus.DONE]} done",  # noqa: E501
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=person_id,
                    entity_type=EntityType.PERSON,
                    title="High org WIP ratio",
                    why_it_matters=f"{in_progress_pct}% of tasks are in progress - teams may be context switching",
                    urgency_score=0.6,
                    goal_tags=[],
                    source_links=[],
                    suggested_action="Consider WIP limits or reprioritization",
                    provenance=[trace.model_dump()],
                )
            )

    # 3. Incident rate
    recent_cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    all_incidents = await _list_ents(db, org_id=org_id, entity_type=EntityType.INCIDENT, limit=50)
    recent_incidents = [i for i in all_incidents if i.created_at and i.created_at >= recent_cutoff]
    if len(recent_incidents) >= 3:
        trace = RecommendationTrace(
            recommendation_id="incident_rate",
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[],
            graph_traces=[
                GraphTrace(
                    traversal_type="incident_rate",
                    path=[],
                    depth=0,
                    entities_visited=len(recent_incidents),
                    description=f"{len(recent_incidents)} incidents in the last 7 days",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=person_id,
                entity_type=EntityType.PERSON,
                title=f"{len(recent_incidents)} incidents this week",
                why_it_matters=f"Elevated incident count - {len(recent_incidents)} in the last 7 days",
                urgency_score=0.75,
                goal_tags=[],
                source_links=[],
                suggested_action="Review incident patterns and root causes",
                provenance=[trace.model_dump()],
            )
        )

    # 4. Cross-team blocking (same as CTO)
    all_report_ids = [r.id for r in direct_reports]
    # Expand to include their reports too
    for report in direct_reports:
        sub_team = await get_team_members(db, report.id)
        all_report_ids.extend([m.id for m in sub_team])

    if all_report_ids:
        cross_blocks = await get_cross_team_blocking(db, org_id, all_report_ids)
        for cb in cross_blocks[:3]:
            blocker = cb.get("blocker_task")
            blocked = cb.get("blocked_task")
            if not blocker or not blocked:
                continue
            if any(item.entity_id == blocker.id for item in items):
                continue
            goal_tags = await _get_goal_tags_for_entity(db, blocker.id, org_id)
            source_links = await _get_source_links(db, blocker.id, org_id)
            trace = RecommendationTrace(
                recommendation_id=str(blocker.id),
                generated_at=str(datetime.now(timezone.utc)),
                source_traces=[_build_source_trace(blocker)],
                graph_traces=[
                    GraphTrace(
                        traversal_type="cross_team_gap",
                        path=[
                            {
                                "entity_id": str(blocker.id),
                                "entity_name": blocker.canonical_name,
                                "edge_type": "blocks",
                            },
                            {
                                "entity_id": str(blocked.id),
                                "entity_name": blocked.canonical_name,
                                "edge_type": "blocked",
                            },
                        ],
                        depth=2,
                        entities_visited=2,
                        description="Cross-team dependency between your teams",
                    )
                ],
            )
            items.append(
                BriefingItem(
                    entity_id=blocker.id,
                    entity_type=EntityType.TASK,
                    title=f"Cross-team dep: {blocker.canonical_name}",
                    why_it_matters=f"Blocks {blocked.canonical_name} on another team",
                    urgency_score=0.75,
                    goal_tags=goal_tags,
                    source_links=source_links,
                    suggested_action="Coordinate across teams",
                    provenance=[trace.model_dump()],
                )
            )

    return items


# ── VP Product briefing ───────────────────────────────────────────────


async def _assemble_vp_product_briefing(
    db: AsyncSession, member: OrgMember, person_entity: Entity
) -> list[BriefingItem]:
    """Gather signals relevant to a VP of Product."""
    items: list[BriefingItem] = []
    org_id = member.org_id

    # 1. Goals with no coverage (no tasks/features linked)
    uncovered_goals = await get_unowned_goals(db, org_id)
    for goal in uncovered_goals[:5]:
        if any(item.entity_id == goal.id for item in items):
            continue
        source_links = await _get_source_links(db, goal.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(goal.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(goal)],
            graph_traces=[
                GraphTrace(
                    traversal_type="goal_no_coverage",
                    path=[{"entity_id": str(goal.id), "entity_name": goal.canonical_name}],
                    depth=0,
                    entities_visited=1,
                    description="No tasks or features are linked to this goal",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=goal.id,
                entity_type=EntityType.GOAL,
                title=f"No coverage: {goal.canonical_name}",
                why_it_matters="This goal has zero tasks or features linked - no one is working toward it",
                urgency_score=0.8,
                goal_tags=[goal.canonical_name],
                source_links=source_links,
                suggested_action="Assign work or re-evaluate this goal",
                provenance=[trace.model_dump()],
            )
        )

    # 2. Launch blockers - features with the most blocked tasks (org-wide)
    from src.graph import list_entities as _list_ents

    all_features = await _list_ents(db, org_id=org_id, entity_type=EntityType.FEATURE, limit=100)
    for feature in all_features:
        if any(item.entity_id == feature.id for item in items):
            continue
        tagged_tasks = await get_entities_via_edge(
            db,
            feature.id,
            EdgeType.TAGGED_TO,
            direction="incoming",
            target_type=EntityType.TASK,
            org_id=org_id,
        )
        blocked_count = 0
        for task in tagged_tasks:
            bc = await count_edges(db, task.id, EdgeType.BLOCKS, direction="outgoing", org_id=org_id)
            if bc > 0:
                blocked_count += 1
        if blocked_count == 0:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, feature.id, org_id)
        source_links = await _get_source_links(db, feature.id, org_id)
        trace = RecommendationTrace(
            recommendation_id=str(feature.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(feature)],
            graph_traces=[
                GraphTrace(
                    traversal_type="launch_blocker",
                    path=[
                        {
                            "entity_id": str(feature.id),
                            "entity_name": feature.canonical_name,
                            "edge_type": "tagged_to",
                        }
                    ],
                    depth=2,
                    entities_visited=blocked_count + 1,
                    description=f"{blocked_count} blocked task(s) under {feature.canonical_name}",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=feature.id,
                entity_type=EntityType.FEATURE,
                title=f"Launch blocker: {feature.canonical_name}",
                why_it_matters=f"{blocked_count} task(s) under this feature are blocked",
                urgency_score=0.75,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Investigate and help resolve blockers",
                provenance=[trace.model_dump()],
            )
        )
        if len([i for i in items if i.entity_type == EntityType.FEATURE]) >= 5:
            break

    # 3. Stale decisions (open >7 days)
    recent_cutoff = datetime.now(timezone.utc) - _RECENT_WINDOW
    all_decisions = await _list_ents(db, org_id=org_id, entity_type=EntityType.DECISION, limit=50)
    for decision in all_decisions:
        if any(item.entity_id == decision.id for item in items):
            continue
        props = decision.properties or {}
        status = props.get("status", "open")
        if status != "open":
            continue
        if decision.created_at and decision.created_at >= recent_cutoff:
            continue  # Not stale yet

        goal_tags = await _get_goal_tags_for_entity(db, decision.id, org_id)
        source_links = await _get_source_links(db, decision.id, org_id)
        days_old = (datetime.now(timezone.utc) - decision.created_at).days if decision.created_at else 0
        trace = RecommendationTrace(
            recommendation_id=str(decision.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(decision)],
            graph_traces=[
                GraphTrace(
                    traversal_type="stale_decision",
                    path=[{"entity_id": str(decision.id), "entity_name": decision.canonical_name}],
                    depth=0,
                    entities_visited=1,
                    description=f"Open decision, {days_old} days old",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=decision.id,
                entity_type=EntityType.DECISION,
                title=f"Stale decision: {decision.canonical_name}",
                why_it_matters=f"This decision has been open for {days_old} days - may be blocking progress",
                urgency_score=0.7,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Drive to resolution or delegate",
                provenance=[trace.model_dump()],
            )
        )
        if len([i for i in items if i.entity_type == EntityType.DECISION]) >= 3:
            break

    # 4. Low adoption features (org-wide)
    for feature in all_features:
        if any(item.entity_id == feature.id for item in items):
            continue
        props = feature.properties or {}
        adoption_rate = props.get("adoption_rate")
        if adoption_rate is None or adoption_rate >= _LOW_ADOPTION_THRESHOLD:
            continue

        goal_tags = await _get_goal_tags_for_entity(db, feature.id, org_id)
        source_links = await _get_source_links(db, feature.id, org_id)
        pct = round(adoption_rate * 100, 1)
        trace = RecommendationTrace(
            recommendation_id=str(feature.id),
            generated_at=str(datetime.now(timezone.utc)),
            source_traces=[_build_source_trace(feature)],
            graph_traces=[
                GraphTrace(
                    traversal_type="low_adoption",
                    path=[{"entity_id": str(feature.id), "entity_name": feature.canonical_name}],
                    depth=0,
                    entities_visited=1,
                    description=f"{pct}% adoption - below {_LOW_ADOPTION_THRESHOLD * 100}% threshold",
                )
            ],
        )
        items.append(
            BriefingItem(
                entity_id=feature.id,
                entity_type=EntityType.FEATURE,
                title=f"Low adoption: {feature.canonical_name}",
                why_it_matters=f"Only {pct}% adoption - may need product attention",
                urgency_score=0.5,
                goal_tags=goal_tags,
                source_links=source_links,
                suggested_action="Investigate adoption barriers",
                provenance=[trace.model_dump()],
            )
        )

    return items


# ── Public API ───────────────────────────────────────────────────────────


async def assemble_briefing(
    db: AsyncSession, member: OrgMember
) -> tuple[list[BriefingItem], str | None]:
    """Assemble a personalized briefing for an org member based on their role.

    Gathers role-appropriate signals from the context graph and urgency
    scores, returning a sorted list of up to 10 BriefingItems paired with
    an optional reason string when the list is empty.

    empty_reason values:
      - "no_person_entity": member isn't linked to a Person node in the graph
      - "no_urgent_signals": assembler ran but found nothing worth surfacing
      - None: items is non-empty
    """
    person_entity = await _get_person_entity(db, member, member.org_id)
    if person_entity is None:
        logger.warning(
            "No person entity linked to member %s (%s), skipping briefing",
            member.id,
            member.email,
        )
        return [], "no_person_entity"

    match member.role:
        case RoleType.ENGINEER:
            items = await _assemble_engineer_briefing(db, member, person_entity)
        case RoleType.DESIGNER:
            items = await _assemble_designer_briefing(db, member, person_entity)
        case RoleType.PM:
            items = await _assemble_pm_briefing(db, member, person_entity)
        case RoleType.EM:
            items = await _assemble_em_briefing(db, member, person_entity)
        case RoleType.CTO:
            items = await _assemble_cto_briefing(db, member, person_entity)
        case RoleType.VP_ENG:
            items = await _assemble_vp_eng_briefing(db, member, person_entity)
        case RoleType.VP_PRODUCT:
            items = await _assemble_vp_product_briefing(db, member, person_entity)
        case _:
            items = await _assemble_engineer_briefing(db, member, person_entity)

    # Sort by urgency descending and cap at limit
    items.sort(key=lambda i: i.urgency_score, reverse=True)
    capped = items[:_MAX_BRIEFING_ITEMS]
    return capped, (None if capped else "no_urgent_signals")
