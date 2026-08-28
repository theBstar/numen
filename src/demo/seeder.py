"""Orchestration for seeding and maintaining demo org data.

Idempotent - safe to run multiple times. Uses deterministic UUIDs so
re-seeding updates existing rows rather than creating duplicates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import ensure_person_entity_for_member
from src.demo.fixtures import (
    CONNECTOR_CONFIGS,
    DECISION_IDS,
    DECISIONS,
    DEMO_ORG_ID,
    DEPLOY_IDS,
    DEPLOYS,
    EDGE_IDS,
    EDGES,
    GOAL_IDS,
    GOALS,
    ORG_MEMBER_IDS,
    ORG_MEMBERS,
    PERSON_BY_KEY,
    PERSON_IDS,
    PR_IDS,
    PROJECT_IDS,
    PROJECTS,
    PRS,
    TASK_IDS,
    TASKS,
    _days_ago,
)
from src.graph import (
    upsert_edge,
    upsert_entity,
)
from src.shared.models import (
    OAuthToken,
    Organization,
    OrgMember,
    SyncState,
)
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    ProgressMode,
    ProjectStatus,
    RoleType,
    SourceType,
    SyncStatus,
)

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Helpers ──────────────────────────────────────────────────────────────


async def _upsert_entity(
    db: AsyncSession,
    entity_id: UUID,
    org_id: UUID,
    entity_type: EntityType,
    source: SourceType,
    source_ids: dict[str, str],
    canonical_name: str,
    properties: dict,
    created_at: datetime | None = None,
) -> UUID:
    """Insert or update an entity using the graph API.

    The fixture-side ``entity_id`` is no longer used as the graph id (FalkorDB
    assigns its own). Returns the real graph id so callers can remap edge
    endpoints.
    """
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=entity_type,
            source=source,
            source_ids=source_ids,
            canonical_name=canonical_name,
            properties=properties,
        ),
    )
    if created_at and entity.created_at != created_at:
        entity.created_at = created_at
        await db.flush()
    return entity.id if isinstance(entity.id, UUID) else UUID(str(entity.id))


async def _upsert_edge(
    db: AsyncSession,
    edge_id: UUID,
    org_id: UUID,
    from_entity_id: UUID,
    to_entity_id: UUID,
    edge_type: EdgeType,
    weight: float = 1.0,
    confidence: float = 1.0,
    evidence: list[dict] | None = None,
) -> None:
    """Insert or update an edge using the graph API.

    The edge_id parameter is kept for API compatibility but the graph API
    uses (from_entity_id, to_entity_id, type) for matching.
    """
    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=from_entity_id,
            to_entity_id=to_entity_id,
            type=EdgeType(edge_type),
            weight=weight,
            confidence=confidence,
            evidence=evidence or [{"source": "demo-seed"}],
        ),
    )


# ── Main seeder ──────────────────────────────────────────────────────────


async def seed_demo_org(db: AsyncSession) -> UUID:
    """Create or find demo org and seed all fixture data. Idempotent.

    Returns the demo org ID.
    """
    logger.info("Seeding demo organization...")

    # 1. Create org if not exists
    result = await db.execute(select(Organization).where(Organization.id == DEMO_ORG_ID))
    org = result.scalar_one_or_none()
    if org is None:
        org = Organization(
            id=DEMO_ORG_ID,
            name="Numen Demo",
            slug="numen-demo",
            is_demo=True,
        )
        db.add(org)
        await db.flush()
        logger.info("Created demo organization: %s", DEMO_ORG_ID)
    else:
        logger.info("Demo organization already exists: %s", DEMO_ORG_ID)

    # Track fixture-id -> real FalkorDB-id remap for edge rewrite below
    id_map: dict[UUID, UUID] = {}

    # 2. Seed persons
    logger.info("Seeding %d persons...", len(PERSON_IDS))
    for person_data in PERSON_BY_KEY.values():
        key = person_data["key"]
        id_map[PERSON_IDS[key]] = await _upsert_entity(
            db,
            entity_id=PERSON_IDS[key],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.PERSON,
            source=SourceType.MANUAL,
            source_ids={
                "email": person_data["email"],
                "github": person_data["github_username"],
                "linear": person_data["linear_id"],
                "slack": person_data["slack_id"],
            },
            canonical_name=person_data["name"],
            properties={
                "email": person_data["email"],
                "role": person_data["role"],
                "title": person_data["title"],
                "team": person_data["team"],
                "github_username": person_data["github_username"],
                "linear_id": person_data["linear_id"],
                "slack_id": person_data["slack_id"],
            },
        )
    await db.flush()

    # 3. Seed tasks
    logger.info("Seeding %d tasks...", len(TASKS))
    for t in TASKS:
        assignee_data = PERSON_BY_KEY[t["assignee"]]
        created_at = datetime.fromisoformat(t["created_at"]) if t.get("created_at") else None
        id_map[TASK_IDS[t["key"]]] = await _upsert_entity(
            db,
            entity_id=TASK_IDS[t["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.TASK,
            source=SourceType.LINEAR,
            source_ids={"linear": t["key"]},
            canonical_name=t["title"],
            properties={
                "title": t["title"],
                "identifier": t["key"],
                "status": t["status"],
                "priority": t["priority"],
                "assignee_email": assignee_data["email"],
                "assignee_name": assignee_data["name"],
                "labels": t["labels"],
                "in_sprint": t["in_sprint"],
                "due_date": t["due_date"],
                "url": f"https://linear.app/demo/issue/{t['key']}",
            },
            created_at=created_at,
        )
    await db.flush()

    # 4. Seed PRs
    logger.info("Seeding %d PRs...", len(PRS))
    for p in PRS:
        author_data = PERSON_BY_KEY[p["author"]]
        created_at = datetime.fromisoformat(p["created_at"]) if p.get("created_at") else None
        id_map[PR_IDS[p["key"]]] = await _upsert_entity(
            db,
            entity_id=PR_IDS[p["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.COMMIT_PR,
            source=SourceType.GITHUB,
            source_ids={"github": str(p["num"]), "sha": p["sha"]},
            canonical_name=p["title"],
            properties={
                "title": p["title"],
                "number": p["num"],
                "state": p["state"],
                "branch": p["branch"],
                "author_email": author_data["email"],
                "author_name": author_data["name"],
                "additions": p["additions"],
                "deletions": p["deletions"],
                "sha": p["sha"],
                "linked_task": p["task_key"],
                "reviewers": [PERSON_BY_KEY[r]["email"] for r in p.get("reviewers", [])],
                "url": f"https://github.com/numen-team/numen/pull/{p['num']}",
            },
            created_at=created_at,
        )
    await db.flush()

    # 5. Seed deploys
    logger.info("Seeding %d deploys...", len(DEPLOYS))
    for d in DEPLOYS:
        created_at = datetime.fromisoformat(d["created_at"]) if d.get("created_at") else None
        id_map[DEPLOY_IDS[d["key"]]] = await _upsert_entity(
            db,
            entity_id=DEPLOY_IDS[d["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.DEPLOY,
            source=SourceType.GITHUB,
            source_ids={"github": f"deploy-{d['num']}", "sha": d["sha"]},
            canonical_name=f"Deploy #{d['num']} to {d['environment']}",
            properties={
                "environment": d["environment"],
                "status": d["status"],
                "sha": d["sha"],
                "duration_seconds": d["duration_seconds"],
                "pr_key": d["pr_key"],
            },
            created_at=created_at,
        )
    await db.flush()

    # 6. Seed goals
    logger.info("Seeding %d goals...", len(GOALS))
    for g in GOALS:
        owner_data = PERSON_BY_KEY[g["owner"]]
        id_map[GOAL_IDS[g["key"]]] = await _upsert_entity(
            db,
            entity_id=GOAL_IDS[g["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.GOAL,
            source=SourceType.MANUAL,
            source_ids={"manual": g["key"]},
            canonical_name=g["title"],
            properties={
                "level": g["level"],
                "status": ProjectStatus.ACTIVE,
                "owner_email": owner_data["email"],
                "owner_name": owner_data["name"],
                "target_value": g["target_value"],
                "current_value": g["current_value"],
                "key_results": g["key_results"],
                "time_bound_start": g["time_bound_start"],
                "time_bound_end": g["time_bound_end"],
                "progress_mode": ProgressMode.MANUAL,
            },
        )
    await db.flush()

    # 7. Seed projects
    logger.info("Seeding %d projects...", len(PROJECTS))
    for proj in PROJECTS:
        owner_data = PERSON_BY_KEY[proj["owner"]]
        id_map[PROJECT_IDS[proj["key"]]] = await _upsert_entity(
            db,
            entity_id=PROJECT_IDS[proj["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.PROJECT,
            source=SourceType.MANUAL,
            source_ids={"manual": proj["key"]},
            canonical_name=proj["name"],
            properties={
                "description": proj["description"],
                "status": proj["status"],
                "owner_email": owner_data["email"],
                "owner_name": owner_data["name"],
                "start_date": proj["start_date"],
                "end_date": proj["end_date"],
            },
        )
    await db.flush()

    # 8. Seed decisions
    logger.info("Seeding %d decisions...", len(DECISIONS))
    for dec in DECISIONS:
        actor_data = PERSON_BY_KEY[dec["actor"]]
        created_at = datetime.fromisoformat(dec["created_at"]) if dec.get("created_at") else None
        id_map[DECISION_IDS[dec["key"]]] = await _upsert_entity(
            db,
            entity_id=DECISION_IDS[dec["key"]],
            org_id=DEMO_ORG_ID,
            entity_type=EntityType.DECISION,
            source=SourceType.MANUAL,
            source_ids={"manual": dec["key"]},
            canonical_name=dec["title"],
            properties={
                "type": dec["type"],
                "actor_email": actor_data["email"],
                "actor_name": actor_data["name"],
                "trigger": dec["trigger"],
                "outcome": dec["outcome"],
            },
            created_at=created_at,
        )
    await db.flush()

    # 9. Seed edges (remap fixture-ids to real FalkorDB ids)
    logger.info("Seeding %d edges...", len(EDGES))
    skipped = 0
    for e in EDGES:
        from_id = id_map.get(e["from_entity_id"])
        to_id = id_map.get(e["to_entity_id"])
        if from_id is None or to_id is None:
            skipped += 1
            continue
        await _upsert_edge(
            db,
            edge_id=EDGE_IDS[e["key"]],
            org_id=DEMO_ORG_ID,
            from_entity_id=from_id,
            to_entity_id=to_id,
            edge_type=e["type"],
            weight=e["weight"],
            confidence=e["confidence"],
        )
    if skipped:
        logger.warning("Skipped %d edges (missing entity in id_map)", skipped)
    await db.flush()

    # 10. Seed org members
    logger.info("Seeding %d org members...", len(ORG_MEMBERS))
    role_map = {
        "engineer": RoleType.ENGINEER,
        "pm": RoleType.PM,
        "em": RoleType.EM,
        "cto": RoleType.CTO,
        "designer": RoleType.DESIGNER,
    }
    for m in ORG_MEMBERS:
        person_data = PERSON_BY_KEY[m["key"]]
        member_id = ORG_MEMBER_IDS[m["key"]]
        real_person_id = id_map.get(PERSON_IDS[m["key"]], PERSON_IDS[m["key"]])

        result = await db.execute(select(OrgMember).where(OrgMember.id == member_id))
        existing = result.scalar_one_or_none()

        if existing is None:
            db.add(
                OrgMember(
                    id=member_id,
                    org_id=DEMO_ORG_ID,
                    person_entity_id=real_person_id,
                    role=role_map.get(m["role"], RoleType.ENGINEER),
                    email=person_data["email"],
                    display_name=person_data["name"],
                    preferences={"notifications": True, "briefing_time": "08:00"},
                    timezone="America/New_York",
                )
            )
        elif existing.person_entity_id != real_person_id:
            existing.person_entity_id = real_person_id
    await db.flush()

    # Repair any non-fixture member (e.g. admin auto-added at login) whose
    # person_entity_id points at a now-gone graph node.
    fixture_emails = {p["email"].lower() for p in PERSON_BY_KEY.values()}
    non_fixture = (
        await db.execute(select(OrgMember).where(OrgMember.org_id == DEMO_ORG_ID))
    ).scalars().all()
    for member in non_fixture:
        if member.email.lower() in fixture_emails:
            continue
        member.person_entity_id = None
        await ensure_person_entity_for_member(db, member)
    await db.flush()

    # 11. Seed OAuth tokens (fake - for connector status display)
    logger.info("Seeding connector configs...")
    source_map = {
        "linear": SourceType.LINEAR,
        "github": SourceType.GITHUB,
        "slack": SourceType.SLACK,
    }
    for cfg in CONNECTOR_CONFIGS:
        source = source_map[cfg["connector"]]
        result = await db.execute(
            select(OAuthToken).where(
                OAuthToken.org_id == DEMO_ORG_ID,
                OAuthToken.connector == source,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            token = OAuthToken(
                org_id=DEMO_ORG_ID,
                connector=source,
                access_token=cfg["access_token"],
                scopes=cfg["scopes"],
            )
            db.add(token)
    await db.flush()

    # 12. Seed sync states showing recent syncs
    logger.info("Seeding sync states...")
    for cfg in CONNECTOR_CONFIGS:
        source = source_map[cfg["connector"]]
        result = await db.execute(
            select(SyncState).where(
                SyncState.org_id == DEMO_ORG_ID,
                SyncState.connector == source,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            sync = SyncState(
                org_id=DEMO_ORG_ID,
                connector=source,
                last_sync_at=_days_ago(cfg["last_sync_days_ago"]),
                status=SyncStatus.IDLE,
                cursor={"demo": True},
            )
            db.add(sync)
        else:
            existing.last_sync_at = _days_ago(cfg["last_sync_days_ago"])
            existing.status = SyncStatus.IDLE
    await db.flush()

    # 13. Commit
    await db.commit()
    logger.info(
        "Demo org seeded successfully: org_id=%s, "
        "%d persons, %d tasks, %d PRs, %d deploys, "
        "%d goals, %d projects, %d decisions, %d edges, %d members",
        DEMO_ORG_ID,
        len(PERSON_IDS),
        len(TASK_IDS),
        len(PR_IDS),
        len(DEPLOY_IDS),
        len(GOAL_IDS),
        len(PROJECT_IDS),
        len(DECISION_IDS),
        len(EDGES),
        len(ORG_MEMBERS),
    )

    return DEMO_ORG_ID


async def apply_daily_variance(db: AsyncSession, org_id: UUID) -> None:
    """Apply daily variance for today."""
    from src.demo.generator import generate_daily_variance

    await generate_daily_variance(db, org_id)
    await db.commit()
