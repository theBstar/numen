"""Redis caching layer for urgency scores."""

from __future__ import annotations

from uuid import UUID

import redis.asyncio as redis

from src.config import settings
from src.shared.types import UrgencyScore


def get_redis() -> redis.Redis:
    """Create a Redis async client from application settings."""
    return redis.from_url(settings.redis_url, decode_responses=True)


def _key(org_id: UUID, person_id: UUID) -> str:
    """Build the sorted-set key for a person's urgency scores."""
    return f"urgency:{org_id}:{person_id}"


def _org_pattern(org_id: UUID) -> str:
    """Glob pattern matching all urgency keys for an org."""
    return f"urgency:{org_id}:*"


async def cache_scores(scores: list[UrgencyScore]) -> None:
    """Write urgency scores to Redis sorted sets.

    Key pattern: ``urgency:{org_id}:{person_id}``
    Score = urgency value.  Member = entity_id as string.
    """
    if not scores:
        return

    client = get_redis()
    try:
        pipe = client.pipeline(transaction=False)
        for s in scores:
            key = _key(s.org_id, s.person_id)
            pipe.zadd(key, {str(s.entity_id): s.score})
        await pipe.execute()
    finally:
        await client.aclose()


async def get_cached_scores(
    org_id: UUID,
    person_id: UUID,
    limit: int = 20,
) -> list[tuple[UUID, float]]:
    """Read top N entity scores from the sorted set (highest first).

    Returns a list of ``(entity_id, score)`` tuples.
    """
    client = get_redis()
    try:
        key = _key(org_id, person_id)
        results = await client.zrevrange(key, 0, limit - 1, withscores=True)
        return [(UUID(member), score) for member, score in results]
    finally:
        await client.aclose()


async def invalidate_person(org_id: UUID, person_id: UUID) -> None:
    """Delete the entire sorted set for a person."""
    client = get_redis()
    try:
        key = _key(org_id, person_id)
        await client.delete(key)
    finally:
        await client.aclose()


async def invalidate_entity(org_id: UUID, entity_id: UUID) -> None:
    """Remove an entity from all person sorted sets in the given org.

    Uses SCAN to iterate over matching keys to avoid blocking the server.
    """
    client = get_redis()
    try:
        pattern = _org_pattern(org_id)
        member = str(entity_id)
        cursor: int | str = 0
        while True:
            cursor, keys = await client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                pipe = client.pipeline(transaction=False)
                for key in keys:
                    pipe.zrem(key, member)
                await pipe.execute()
            if cursor == 0:
                break
    finally:
        await client.aclose()
