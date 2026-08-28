"""Dashboard summary route."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.rbac import (
    CROSS_BLOCK_ROLES as _CROSS_BLOCK_ROLES,
)
from src.api.rbac import (
    DELAYED_ROLES as _DELAYED_ROLES,
)
from src.api.rbac import (
    GOALS_ROLES as _GOALS_ROLES,
)
from src.api.rbac import (
    INCIDENT_ROLES as _INCIDENT_ROLES,
)
from src.api.rbac import (
    TEAM_ROLES as _TEAM_ROLES,
)
from src.api.schemas import (
    DashboardSummaryResponse,
    DelayedProjectItem,
    GoalsSummary,
    TaskCountsResponse,
    TeamMemberWorkload,
)
from src.graph import (
    get_cross_team_blocking,
    get_goal_coverage,
    get_person_workload_hybrid,
    get_project_stats,
    get_stalled_prs,
    get_team_members,
    get_team_workload_summary,
    upsert_edge,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.shared.models import Organization, OrgMember
from src.shared.types import EdgeCreate, EdgeType, EntityType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get(
    "/orgs/{org_id}/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["dashboard"],
)
async def get_dashboard_summary(
    org: Organization = Depends(get_org),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Return a role-aware dashboard summary for the current member."""
    role = member.role
    person_id = member.person_entity_id
    org_id = org.id

    # If the member has no linked person entity, return empty defaults
    if person_id is None:
        return DashboardSummaryResponse(role=role)

    # ── Lazy edge repair: backfill ASSIGNED_TO edges for tasks that
    #    have assignee_email in properties but no edge to this person.
    try:
        orphan_stmt = text("""
            SELECT e.id FROM entities e
            WHERE e.org_id = :org_id
              AND e.type = 'TASK'
              AND e.properties->>'assignee_email' = :email
              AND NOT EXISTS (
                  SELECT 1 FROM edges ed
                  WHERE ed.to_entity_id = e.id
                    AND ed.from_entity_id = :person_id
                    AND ed.type = 'ASSIGNED_TO'
              )
        """)
        orphan_result = await db.execute(
            orphan_stmt,
            {
                "org_id": str(org_id),
                "email": member.email,
                "person_id": str(person_id),
            },
        )
        orphan_task_ids = [row[0] for row in orphan_result.fetchall()]
        if orphan_task_ids:
            for tid in orphan_task_ids:
                await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=person_id,
                        to_entity_id=tid,
                        type=EdgeType.ASSIGNED_TO,
                        weight=1.0,
                        confidence=1.0,
                        evidence=[{"source": "dashboard_edge_repair"}],
                    ),
                )
            await db.commit()
    except Exception:
        logger.warning("Dashboard edge repair failed", exc_info=True)

    # ── Always: my_tasks + pr_reviews_pending ─────────────────────
    workload = await get_person_workload_hybrid(db, person_id, email=member.email)
    my_tasks = TaskCountsResponse(
        active=workload.get("in_progress", 0),
        in_review=workload.get("in_review", 0),
        todo=workload.get("todo", 0),
        blocked=workload.get("blocked", 0),
        total=workload.get("total", 0),
    )

    # Count open PRs where this person is a reviewer.
    pr_review_stmt = text("""
        SELECT COUNT(*) FROM edges e
        JOIN entities ent ON ent.id = e.to_entity_id
        WHERE e.from_entity_id = :person_id
          AND e.type = 'reviews'
          AND ent.type = 'COMMIT_PR'
          AND ent.properties->>'status' = 'open'
    """)
    try:
        pr_result = await db.execute(pr_review_stmt, {"person_id": str(person_id)})
        pr_reviews_pending = pr_result.scalar_one()
    except Exception:
        await db.rollback()
        pr_reviews_pending = 0

    # ── Goals summary (PM, CTO, VP_ENG, VP_PRODUCT) ──────────────
    goals_summary: GoalsSummary | None = None
    if role in _GOALS_ROLES:
        coverage = await get_goal_coverage(db, org_id)
        total = len(coverage)
        no_coverage = sum(1 for g in coverage if g.get("task_count", 0) == 0)
        on_track = sum(1 for g in coverage if g.get("task_count", 0) > 0 and g.get("feature_count", 0) > 0)
        at_risk = total - on_track - no_coverage
        goals_summary = GoalsSummary(
            total=total,
            on_track=on_track,
            at_risk=at_risk,
            no_coverage=no_coverage,
        )

    # ── Team workload + stalled PRs (EM, CTO, VP_ENG) ────────────
    team_workload_list: list[TeamMemberWorkload] | None = None
    team_size = 0
    stalled_prs_count = 0
    team_person_ids: list[UUID] = []

    if role in _TEAM_ROLES:
        team_summary = await get_team_workload_summary(db, person_id)
        members_data = team_summary.get("members", {})
        team_workload_list = [
            TeamMemberWorkload(
                person_id=str(pid),
                person_name=data.get("name", ""),
                todo=data.get("todo", 0),
                in_progress=data.get("in_progress", 0),
                in_review=data.get("in_review", 0),
                done=data.get("done", 0),
                total=data.get("total", 0),
            )
            for pid, data in members_data.items()
        ]
        team_size = len(team_workload_list)

        team_members = await get_team_members(db, person_id)
        team_person_ids = [m.id for m in team_members]
        if team_person_ids:
            try:
                stalled = await get_stalled_prs(db, org_id, team_person_ids)
                stalled_prs_count = len(stalled)
            except Exception:
                await db.rollback()
                stalled_prs_count = 0

    # ── Delayed projects (EM, CTO, VP_ENG, VP_PRODUCT) ────────────
    delayed_projects: list[DelayedProjectItem] | None = None
    if role in _DELAYED_ROLES:
        all_projects = await graph_list_entities(db, org_id, entity_type=EntityType.PROJECT, limit=500)
        now_utc = datetime.now(timezone.utc)

        delayed_items: list[DelayedProjectItem] = []
        for proj in all_projects:
            props = proj.properties or {}
            status = props.get("status", "")
            if status not in ("planning", "active"):
                continue
            end_date_str = props.get("end_date", "")
            if not end_date_str:
                continue
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if end_dt >= now_utc:
                continue

            days_overdue = (now_utc - end_dt).days
            stats = await get_project_stats(db, proj.id, org_id=org_id)
            remaining = stats.get("total", 0) - stats.get("done", 0)

            delayed_items.append(
                DelayedProjectItem(
                    id=str(proj.id),
                    name=proj.canonical_name,
                    days_overdue=max(days_overdue, 0),
                    remaining_tasks=max(remaining, 0),
                )
            )
        delayed_projects = delayed_items

    # ── Cross-team blocks (EM, CTO, VP_ENG) ───────────────────────
    cross_team_blocks = 0
    if role in _CROSS_BLOCK_ROLES and team_person_ids:
        blocks = await get_cross_team_blocking(db, org_id, team_person_ids)
        cross_team_blocks = len(blocks)

    # ── Recent incidents (ENGINEER, VP_ENG) ───────────────────────
    recent_incidents_count = 0
    if role in _INCIDENT_ROLES:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        all_incidents = await graph_list_entities(db, org_id, entity_type=EntityType.INCIDENT, limit=500)
        recent_incidents_count = sum(1 for inc in all_incidents if inc.created_at and inc.created_at >= week_ago)

    return DashboardSummaryResponse(
        role=role,
        my_tasks=my_tasks,
        pr_reviews_pending=pr_reviews_pending,
        goals_summary=goals_summary,
        team_workload=team_workload_list,
        team_size=team_size,
        delayed_projects=delayed_projects,
        stalled_prs_count=stalled_prs_count,
        cross_team_blocks=cross_team_blocks,
        recent_incidents_count=recent_incidents_count,
    )
