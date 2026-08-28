"""Turn the names people say into the IDs the graph stores.

MCP tools take UUIDs, because agents pass around identifiers. People say
"the checkout project". These helpers bridge the two, and - importantly -
report ambiguity back to the model as a question rather than guessing.
"""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import list_entities
from src.shared.models import Entity
from src.shared.types import EntityType

_MAX_CANDIDATES = 5


async def resolve_entity(
    db: AsyncSession,
    org_id: UUID,
    entity_type: EntityType,
    name: str,
) -> tuple[Entity | None, str | None]:
    """Resolve one entity by name.

    Returns ``(entity, None)`` on a unique match, or ``(None, error_json)``
    when nothing matches or several do. Listing the candidates lets the model
    ask which one rather than silently picking the first.
    """
    label = entity_type.value.replace("_", " ")
    matches = await list_entities(
        db,
        org_id,
        entity_type=entity_type,
        search=name,
        limit=_MAX_CANDIDATES,
    )
    if not matches:
        return None, json.dumps({"error": f"No {label} matching '{name}' was found."})

    if len(matches) > 1:
        exact = [m for m in matches if m.canonical_name.lower() == name.lower()]
        if len(exact) == 1:
            return exact[0], None
        names = [m.canonical_name for m in matches]
        return None, json.dumps(
            {
                "error": f"Several {label} entries match '{name}'.",
                "candidates": names,
                "hint": "Ask the user which one they mean, then call this tool again with the exact name.",
            }
        )

    return matches[0], None


async def resolve_person(db: AsyncSession, org_id: UUID, name: str):
    return await resolve_entity(db, org_id, EntityType.PERSON, name)


async def resolve_project(db: AsyncSession, org_id: UUID, name: str):
    return await resolve_entity(db, org_id, EntityType.PROJECT, name)


async def resolve_goal(db: AsyncSession, org_id: UUID, name: str):
    return await resolve_entity(db, org_id, EntityType.GOAL, name)


async def resolve_task(db: AsyncSession, org_id: UUID, name: str):
    return await resolve_entity(db, org_id, EntityType.TASK, name)
