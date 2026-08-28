"""MCP resource definitions - static-ish data summaries."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import get_entities_by_ids, get_goal_coverage, get_goal_tree
from src.mcp.serializers import urgency_score_to_dict
from src.shared.models import Entity, OAuthToken, Organization, OrgMember, UrgencyScoreCache


async def get_org_overview(db: AsyncSession, org_id: UUID) -> str:
    """Org summary: name, member count, entity counts by type, connector status."""
    # Org details
    org = await db.get(Organization, org_id)
    if org is None:
        return json.dumps({"error": "Organization not found"})

    # Member count
    stmt = select(func.count(OrgMember.id)).where(OrgMember.org_id == org_id)
    member_count = (await db.execute(stmt)).scalar() or 0

    # Entity counts by type
    stmt = (
        select(Entity.type, func.count(Entity.id))
        .where(Entity.org_id == org_id, Entity.merged_into.is_(None))
        .group_by(Entity.type)
    )
    rows = (await db.execute(stmt)).all()
    entity_counts = {row[0].value: row[1] for row in rows}

    # Connector status
    stmt = select(OAuthToken.connector).where(OAuthToken.org_id == org_id)
    tokens = (await db.execute(stmt)).scalars().all()
    connected_sources = [t.value for t in tokens]

    return json.dumps(
        {
            "name": org.name,
            "slug": org.slug,
            "member_count": member_count,
            "entity_counts": entity_counts,
            "connected_sources": connected_sources,
        },
        default=str,
    )


async def get_org_goals(db: AsyncSession, org_id: UUID) -> str:
    """Goal tree with coverage stats."""
    tree = await get_goal_tree(db, org_id)
    coverage = await get_goal_coverage(db, org_id)
    return json.dumps({"goal_tree": tree, "coverage": coverage}, default=str)


async def get_urgent_tasks(db: AsyncSession, org_id: UUID) -> str:
    """Top 20 urgent tasks across the org."""
    stmt = (
        select(UrgencyScoreCache)
        .where(UrgencyScoreCache.org_id == org_id)
        .order_by(UrgencyScoreCache.score.desc())
        .limit(20)
    )
    result = await db.execute(stmt)
    scores = list(result.scalars().all())

    entity_ids = [s.entity_id for s in scores]
    entities = await get_entities_by_ids(db, entity_ids)
    entity_map = {e.id: e for e in entities}

    items = []
    for s in scores:
        entity = entity_map.get(s.entity_id)
        items.append(urgency_score_to_dict(s, entity))
    return json.dumps(items, default=str)
