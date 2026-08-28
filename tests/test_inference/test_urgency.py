"""Tests for urgency scoring engine."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.inference.urgency import (
    WEIGHTS,
    _downstream_blocked_count,
    _goal_criticality,
    _is_blocking_factor,
    _is_in_current_sprint,
    _mention_count_24h,
    _staleness_factor,
    compute_batch,
    compute_urgency,
)
from src.shared.types import EdgeType, EntityType, UrgencyScore


@pytest.fixture
def org_id():
    return uuid.uuid4()


# ---- Weight configuration tests ----


def test_weights_sum_to_one():
    """Ensure all urgency weights sum to 1.0."""
    assert abs(sum(WEIGHTS.values()) - 1.0) < 0.01


def test_weights_all_positive():
    """Every weight should be positive."""
    for name, weight in WEIGHTS.items():
        assert weight > 0, f"Weight {name} is non-positive: {weight}"


def test_weights_has_expected_keys():
    """Ensure the expected factor keys are present."""
    expected = {
        "staleness_days",
        "is_blocking_others",
        "downstream_blocked_count",
        "mention_count_24h",
        "goal_criticality",
        "is_in_current_sprint",
    }
    assert set(WEIGHTS.keys()) == expected


def test_blocking_has_highest_weight():
    """is_blocking_others should have the highest weight."""
    max_key = max(WEIGHTS, key=WEIGHTS.get)
    assert max_key == "is_blocking_others"


# ---- _staleness_factor tests ----


def _mock_entity(updated_at):
    entity = MagicMock()
    entity.updated_at = updated_at
    return entity


@pytest.mark.asyncio
async def test_staleness_very_fresh(org_id):
    """An entity updated 1 hour ago should have near-zero staleness."""
    db = AsyncMock()
    entity = _mock_entity(datetime.now(timezone.utc) - timedelta(hours=1))

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _staleness_factor(db, uuid.uuid4(), org_id)
    assert score < 0.01
    assert info["factor"] == "staleness_days"


@pytest.mark.asyncio
async def test_staleness_half_cap(org_id):
    """An entity updated 7 days ago should be about 0.5."""
    db = AsyncMock()
    entity = _mock_entity(datetime.now(timezone.utc) - timedelta(days=7))

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _staleness_factor(db, uuid.uuid4(), org_id)
    assert 0.45 < score < 0.55


@pytest.mark.asyncio
async def test_staleness_at_cap(org_id):
    """An entity updated exactly at the cap (14 days) should be ~1.0."""
    db = AsyncMock()
    entity = _mock_entity(datetime.now(timezone.utc) - timedelta(days=14))

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _staleness_factor(db, uuid.uuid4(), org_id)
    assert score >= 0.99


@pytest.mark.asyncio
async def test_staleness_beyond_cap(org_id):
    """An entity updated 30 days ago should still be capped at 1.0."""
    db = AsyncMock()
    entity = _mock_entity(datetime.now(timezone.utc) - timedelta(days=30))

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _staleness_factor(db, uuid.uuid4(), org_id)
    assert score <= 1.0
    assert score >= 0.99


@pytest.mark.asyncio
async def test_staleness_entity_not_found(org_id):
    """If entity is not found, staleness should be 0."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_entity", return_value=None):
        score, info = await _staleness_factor(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert "not found" in info.get("note", "")


@pytest.mark.asyncio
async def test_staleness_passes_org_id(org_id):
    """_staleness_factor must pass org_id to get_entity."""
    db = AsyncMock()
    entity = _mock_entity(datetime.now(timezone.utc))
    eid = uuid.uuid4()

    with patch("src.inference.urgency.get_entity", return_value=entity) as mock_get:
        await _staleness_factor(db, eid, org_id)
    mock_get.assert_called_once_with(db, eid, org_id=org_id)


# ---- _is_blocking_factor tests ----


@pytest.mark.asyncio
async def test_blocking_with_blocks(org_id):
    """If entity blocks other items, score should be 1.0."""
    db = AsyncMock()
    blocked_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=blocked_ids):
        score, info = await _is_blocking_factor(db, uuid.uuid4(), org_id)
    assert score == 1.0
    assert info["blocked_count"] == 3


@pytest.mark.asyncio
async def test_blocking_no_blocks(org_id):
    """If entity blocks nothing, score should be 0.0."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]):
        score, info = await _is_blocking_factor(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert info["blocked_count"] == 0


@pytest.mark.asyncio
async def test_blocking_single_block(org_id):
    """Single blocked item still gives 1.0."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[uuid.uuid4()]):
        score, info = await _is_blocking_factor(db, uuid.uuid4(), org_id)
    assert score == 1.0
    assert info["blocked_count"] == 1


@pytest.mark.asyncio
async def test_blocking_passes_org_id(org_id):
    """_is_blocking_factor must pass org_id to get_connected_entity_ids."""
    db = AsyncMock()
    eid = uuid.uuid4()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]) as mock_fn:
        await _is_blocking_factor(db, eid, org_id)
    mock_fn.assert_called_once_with(db, eid, EdgeType.BLOCKS, direction="outgoing", org_id=org_id)


# ---- _downstream_blocked_count tests ----


@pytest.mark.asyncio
async def test_downstream_no_chain(org_id):
    """No transitive blocking chain should yield 0."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]):
        score, info = await _downstream_blocked_count(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert info["chain_length"] == 0


@pytest.mark.asyncio
async def test_downstream_chain_depth_1(org_id):
    """A chain of depth 1 (one level of blocking)."""
    db = AsyncMock()
    downstream_id = uuid.uuid4()

    call_count = 0

    async def mock_get_ids(db, entity_id, edge_type, direction="outgoing", *, org_id=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [downstream_id]
        return []

    with patch("src.inference.urgency.get_connected_entity_ids", side_effect=mock_get_ids):
        score, info = await _downstream_blocked_count(db, uuid.uuid4(), org_id)
    assert score > 0
    assert info["transitive_blocked_count"] == 1


@pytest.mark.asyncio
async def test_downstream_passes_org_id(org_id):
    """_downstream_blocked_count must pass org_id to get_connected_entity_ids."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]) as mock_fn:
        await _downstream_blocked_count(db, uuid.uuid4(), org_id)
    assert mock_fn.call_args.kwargs["org_id"] == org_id


# ---- _mention_count_24h tests ----


@pytest.mark.asyncio
async def test_mention_count_zero():
    """No mentions should yield 0."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = 0
    db.execute.return_value = result

    score, info = await _mention_count_24h(db, uuid.uuid4())
    assert score == 0.0
    assert info["mention_count"] == 0


@pytest.mark.asyncio
async def test_mention_count_moderate():
    """5 mentions out of 10 cap should be 0.5."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = 5
    db.execute.return_value = result

    score, info = await _mention_count_24h(db, uuid.uuid4())
    assert score == 0.5
    assert info["mention_count"] == 5


@pytest.mark.asyncio
async def test_mention_count_at_cap():
    """10 mentions should max out at 1.0."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = 10
    db.execute.return_value = result

    score, info = await _mention_count_24h(db, uuid.uuid4())
    assert score == 1.0


@pytest.mark.asyncio
async def test_mention_count_beyond_cap():
    """More than 10 mentions should still be capped at 1.0."""
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one.return_value = 25
    db.execute.return_value = result

    score, info = await _mention_count_24h(db, uuid.uuid4())
    assert score == 1.0


# ---- _goal_criticality tests ----


@pytest.mark.asyncio
async def test_goal_criticality_no_goals(org_id):
    """Entity not linked to any goal should have 0 criticality."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]):
        score, goal_ids, info = await _goal_criticality(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert goal_ids == []
    assert info["goals_found"] == 0


@pytest.mark.asyncio
async def test_goal_criticality_with_gap(org_id):
    """Entity linked to a goal with a 50% gap should have 0.5 criticality."""
    db = AsyncMock()
    entity_id = uuid.uuid4()
    goal_id = uuid.uuid4()

    mock_goal = MagicMock()
    mock_goal.id = goal_id
    mock_goal.type = EntityType.GOAL
    mock_goal.canonical_name = "Test Goal"
    mock_goal.properties = {"target_value": 100, "current_value": 50}

    with (
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[goal_id]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[mock_goal]),
    ):
        score, goal_ids, info = await _goal_criticality(db, entity_id, org_id)
    assert score == 0.5
    assert goal_id in goal_ids


@pytest.mark.asyncio
async def test_goal_criticality_goal_on_track(org_id):
    """If a goal is at its target, criticality should be 0."""
    db = AsyncMock()
    goal_id = uuid.uuid4()

    mock_goal = MagicMock()
    mock_goal.id = goal_id
    mock_goal.type = EntityType.GOAL
    mock_goal.canonical_name = "On Track Goal"
    mock_goal.properties = {"target_value": 100, "current_value": 100}

    with (
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[goal_id]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[mock_goal]),
    ):
        score, goal_ids, info = await _goal_criticality(db, uuid.uuid4(), org_id)
    assert score == 0.0


@pytest.mark.asyncio
async def test_goal_criticality_no_goal_entities_found(org_id):
    """Edge points to non-goal entities - should return 0."""
    db = AsyncMock()

    with (
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[uuid.uuid4()]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[]),
    ):
        score, goal_ids, info = await _goal_criticality(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert goal_ids == []


@pytest.mark.asyncio
async def test_goal_criticality_missing_values(org_id):
    """Goal without target/current values should not raise, gap stays 0."""
    db = AsyncMock()
    goal_id = uuid.uuid4()

    mock_goal = MagicMock()
    mock_goal.id = goal_id
    mock_goal.type = EntityType.GOAL
    mock_goal.canonical_name = "Bare Goal"
    mock_goal.properties = {}

    with (
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[goal_id]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[mock_goal]),
    ):
        score, goal_ids, info = await _goal_criticality(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert goal_id in goal_ids


@pytest.mark.asyncio
async def test_goal_criticality_passes_org_id(org_id):
    """_goal_criticality must pass org_id to graph functions."""
    db = AsyncMock()
    eid = uuid.uuid4()

    with patch("src.inference.urgency.get_connected_entity_ids", return_value=[]) as mock_ids:
        await _goal_criticality(db, eid, org_id)
    assert mock_ids.call_args.kwargs["org_id"] == org_id


# ---- _is_in_current_sprint tests ----


@pytest.mark.asyncio
async def test_sprint_in_sprint(org_id):
    """Entity marked as in current sprint should return 1.0."""
    db = AsyncMock()
    entity = MagicMock()
    entity.properties = {"is_in_current_sprint": True, "sprint_name": "Sprint 42"}

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _is_in_current_sprint(db, uuid.uuid4(), org_id)
    assert score == 1.0
    assert info["in_sprint"] is True


@pytest.mark.asyncio
async def test_sprint_not_in_sprint(org_id):
    """Entity not in sprint should return 0.0."""
    db = AsyncMock()
    entity = MagicMock()
    entity.properties = {"status": "in_progress"}

    with patch("src.inference.urgency.get_entity", return_value=entity):
        score, info = await _is_in_current_sprint(db, uuid.uuid4(), org_id)
    assert score == 0.0
    assert info["in_sprint"] is False


@pytest.mark.asyncio
async def test_sprint_entity_not_found(org_id):
    """Entity not found should return 0.0."""
    db = AsyncMock()

    with patch("src.inference.urgency.get_entity", return_value=None):
        score, info = await _is_in_current_sprint(db, uuid.uuid4(), org_id)
    assert score == 0.0


@pytest.mark.asyncio
async def test_sprint_passes_org_id(org_id):
    """_is_in_current_sprint must pass org_id to get_entity."""
    db = AsyncMock()
    eid = uuid.uuid4()
    entity = MagicMock()
    entity.properties = {}

    with patch("src.inference.urgency.get_entity", return_value=entity) as mock_get:
        await _is_in_current_sprint(db, eid, org_id)
    mock_get.assert_called_once_with(db, eid, org_id=org_id)


# ---- compute_urgency tests ----


@pytest.mark.asyncio
async def test_compute_urgency_returns_urgency_score():
    """compute_urgency should return a valid UrgencyScore."""
    db = AsyncMock()
    entity_id = uuid.uuid4()
    person_id = uuid.uuid4()
    org_id = uuid.uuid4()

    entity = MagicMock()
    entity.updated_at = datetime.now(timezone.utc) - timedelta(days=7)
    entity.properties = {}

    mention_result = MagicMock()
    mention_result.scalar_one.return_value = 0
    db.execute.return_value = mention_result

    with (
        patch("src.inference.urgency.get_entity", return_value=entity),
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[]),
    ):
        score = await compute_urgency(db, entity_id, person_id, org_id)

    assert isinstance(score, UrgencyScore)
    assert score.entity_id == entity_id
    assert score.person_id == person_id
    assert score.org_id == org_id
    assert 0 <= score.score <= 100
    assert "staleness_days" in score.components
    assert len(score.provenance) == 6


@pytest.mark.asyncio
async def test_compute_urgency_max_score():
    """All factors at max should produce a score near 100."""
    db = AsyncMock()
    entity_id = uuid.uuid4()
    person_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Staleness: 30 days old
    stale_entity = MagicMock()
    stale_entity.updated_at = datetime.now(timezone.utc) - timedelta(days=30)
    stale_entity.properties = {"is_in_current_sprint": True, "sprint_name": "S42"}

    # Goal with 100% gap
    goal_id = uuid.uuid4()
    mock_goal = MagicMock()
    mock_goal.id = goal_id
    mock_goal.type = EntityType.GOAL
    mock_goal.canonical_name = "Big Goal"
    mock_goal.properties = {"target_value": 100, "current_value": 0}

    # Mentions: 15
    mention_result = MagicMock()
    mention_result.scalar_one.return_value = 15
    db.execute.return_value = mention_result

    call_count = 0

    async def mock_get_ids(db, entity_id, edge_type, direction="outgoing", *, org_id=None):
        nonlocal call_count
        call_count += 1
        if edge_type == EdgeType.BLOCKS and call_count <= 2:
            return [uuid.uuid4()]
        if edge_type == EdgeType.TAGGED_TO:
            return [goal_id]
        return []

    with (
        patch("src.inference.urgency.get_entity", return_value=stale_entity),
        patch("src.inference.urgency.get_connected_entity_ids", side_effect=mock_get_ids),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[mock_goal]),
    ):
        score = await compute_urgency(db, entity_id, person_id, org_id)

    assert score.score >= 80


@pytest.mark.asyncio
async def test_compute_batch_calls_compute_urgency():
    """compute_batch should return one score per entity_id."""
    db = AsyncMock()
    entity_ids = [uuid.uuid4(), uuid.uuid4()]
    person_id = uuid.uuid4()
    org_id = uuid.uuid4()

    entity = MagicMock()
    entity.updated_at = datetime.now(timezone.utc) - timedelta(days=1)
    entity.properties = {}

    mention_result = MagicMock()
    mention_result.scalar_one.return_value = 0
    db.execute.return_value = mention_result

    with (
        patch("src.inference.urgency.get_entity", return_value=entity),
        patch("src.inference.urgency.get_connected_entity_ids", return_value=[]),
        patch("src.inference.urgency.get_entities_by_ids", return_value=[]),
    ):
        scores = await compute_batch(db, org_id, person_id, entity_ids)

    assert len(scores) == 2
    assert all(isinstance(s, UrgencyScore) for s in scores)
