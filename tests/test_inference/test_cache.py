"""Tests for Redis caching layer for urgency scores."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.inference.cache import (
    _key,
    _org_pattern,
    cache_scores,
    get_cached_scores,
    invalidate_entity,
    invalidate_person,
)
from src.shared.types import UrgencyScore


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def person_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000010")


@pytest.fixture
def entity_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000020")


# ---- Key helpers ----


def test_key_format(org_id, person_id):
    """Key should follow the pattern urgency:{org_id}:{person_id}."""
    key = _key(org_id, person_id)
    assert key == f"urgency:{org_id}:{person_id}"


def test_org_pattern_format(org_id):
    """Org pattern should be a glob matching all persons in the org."""
    pattern = _org_pattern(org_id)
    assert pattern == f"urgency:{org_id}:*"


# ---- cache_scores ----


@pytest.mark.asyncio
async def test_cache_scores_empty():
    """Caching empty list should be a no-op."""
    # Should not raise
    with patch("src.inference.cache.get_redis") as mock_redis_factory:
        await cache_scores([])
        mock_redis_factory.assert_not_called()


@pytest.mark.asyncio
async def test_cache_scores_writes_to_sorted_set(org_id, person_id, entity_id):
    """cache_scores should write entity scores as sorted set members."""
    mock_client = AsyncMock()
    mock_pipe = AsyncMock()
    mock_client.pipeline = MagicMock(return_value=mock_pipe)
    mock_pipe.zadd = MagicMock()
    mock_pipe.execute = AsyncMock()

    score = UrgencyScore(
        entity_id=entity_id,
        person_id=person_id,
        org_id=org_id,
        score=75.5,
        components={},
        goal_ids=[],
        provenance=[],
        computed_at=datetime.now(timezone.utc),
    )

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await cache_scores([score])

    mock_pipe.zadd.assert_called_once()
    # Verify the key and the member/score pair
    call_args = mock_pipe.zadd.call_args
    expected_key = _key(org_id, person_id)
    assert call_args[0][0] == expected_key
    assert str(entity_id) in call_args[0][1]
    mock_pipe.execute.assert_awaited_once()
    mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_scores_multiple(org_id, person_id):
    """Caching multiple scores should call zadd for each."""
    mock_client = AsyncMock()
    mock_pipe = AsyncMock()
    mock_client.pipeline = MagicMock(return_value=mock_pipe)
    mock_pipe.zadd = MagicMock()
    mock_pipe.execute = AsyncMock()

    scores = [
        UrgencyScore(
            entity_id=uuid.uuid4(),
            person_id=person_id,
            org_id=org_id,
            score=float(i * 10),
            components={},
            goal_ids=[],
            provenance=[],
            computed_at=datetime.now(timezone.utc),
        )
        for i in range(3)
    ]

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await cache_scores(scores)

    assert mock_pipe.zadd.call_count == 3


# ---- get_cached_scores ----


@pytest.mark.asyncio
async def test_get_cached_scores_empty(org_id, person_id):
    """Empty cache should return empty list."""
    mock_client = AsyncMock()
    mock_client.zrevrange.return_value = []

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        result = await get_cached_scores(org_id, person_id)

    assert result == []
    mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_cached_scores_returns_tuples(org_id, person_id):
    """Cached results should be returned as (UUID, float) tuples."""
    eid = uuid.uuid4()
    mock_client = AsyncMock()
    mock_client.zrevrange.return_value = [(str(eid), 85.0)]

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        result = await get_cached_scores(org_id, person_id)

    assert len(result) == 1
    assert result[0][0] == eid
    assert result[0][1] == 85.0


@pytest.mark.asyncio
async def test_get_cached_scores_limit(org_id, person_id):
    """Limit parameter should be passed to zrevrange."""
    mock_client = AsyncMock()
    mock_client.zrevrange.return_value = []

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await get_cached_scores(org_id, person_id, limit=5)

    # zrevrange called with (key, 0, limit-1, ...)
    call_args = mock_client.zrevrange.call_args
    assert call_args[0][2] == 4  # limit - 1


# ---- invalidate_person ----


@pytest.mark.asyncio
async def test_invalidate_person_deletes_key(org_id, person_id):
    """invalidate_person should delete the sorted set for that person."""
    mock_client = AsyncMock()

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await invalidate_person(org_id, person_id)

    expected_key = _key(org_id, person_id)
    mock_client.delete.assert_awaited_once_with(expected_key)
    mock_client.aclose.assert_awaited_once()


# ---- invalidate_entity ----


@pytest.mark.asyncio
async def test_invalidate_entity_removes_from_all_sets(org_id, entity_id):
    """invalidate_entity should remove the entity from all person sets in the org."""
    mock_client = AsyncMock()
    # First SCAN returns keys, second SCAN returns 0 cursor (done)
    mock_client.scan.side_effect = [
        (0, [f"urgency:{org_id}:person1", f"urgency:{org_id}:person2"]),
    ]
    mock_pipe = AsyncMock()
    mock_client.pipeline = MagicMock(return_value=mock_pipe)
    mock_pipe.zrem = MagicMock()
    mock_pipe.execute = AsyncMock()

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await invalidate_entity(org_id, entity_id)

    assert mock_pipe.zrem.call_count == 2
    mock_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidate_entity_no_keys(org_id, entity_id):
    """If no keys match, invalidate_entity should still complete."""
    mock_client = AsyncMock()
    mock_client.scan.return_value = (0, [])

    with patch("src.inference.cache.get_redis", return_value=mock_client):
        await invalidate_entity(org_id, entity_id)

    mock_client.aclose.assert_awaited_once()
