"""Tests for score orchestration module."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.inference.scorer import (
    _SCORABLE_TYPES,
    _get_entities_for_person,
    _get_org_members,
    _get_people_for_entities,
    get_top_urgent,
    score_delta,
)
from src.shared.types import EdgeType, EntityType, RoleType, UrgencyScore


def test_scorable_types():
    """Only TASK, COMMIT_PR, and INCIDENT should be scorable."""
    assert EntityType.TASK in _SCORABLE_TYPES
    assert EntityType.COMMIT_PR in _SCORABLE_TYPES
    assert EntityType.INCIDENT in _SCORABLE_TYPES
    assert EntityType.PERSON not in _SCORABLE_TYPES
    assert EntityType.GOAL not in _SCORABLE_TYPES


@pytest.mark.asyncio
async def test_get_org_members():
    """Should return OrgMember objects with linked person entities."""
    db = AsyncMock()
    member = MagicMock()
    member.person_entity_id = uuid.uuid4()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [member]
    db.execute.return_value = result

    members = await _get_org_members(db, uuid.uuid4())
    assert len(members) == 1


@pytest.mark.asyncio
async def test_get_entities_for_person():
    """Should return entity IDs of scorable items owned by person."""
    db = AsyncMock()
    org_id = uuid.uuid4()
    person_id = uuid.uuid4()

    task_entity = MagicMock()
    task_entity.id = uuid.uuid4()
    task_entity.type = EntityType.TASK

    pr_entity = MagicMock()
    pr_entity.id = uuid.uuid4()
    pr_entity.type = EntityType.COMMIT_PR

    with patch(
        "src.inference.scorer.get_entities_via_edge", return_value=[task_entity, pr_entity]
    ) as mock_fn:
        entity_ids = await _get_entities_for_person(db, org_id, person_id)

    assert len(entity_ids) == 2
    assert task_entity.id in entity_ids
    assert pr_entity.id in entity_ids
    # Verify org_id is passed
    mock_fn.assert_called_once_with(
        db, person_id, EdgeType.OWNS, direction="outgoing", org_id=org_id
    )


@pytest.mark.asyncio
async def test_get_entities_for_person_filters_non_scorable():
    """Should filter out non-scorable entity types like PERSON, GOAL."""
    db = AsyncMock()
    org_id = uuid.uuid4()
    person_id = uuid.uuid4()

    task_entity = MagicMock()
    task_entity.id = uuid.uuid4()
    task_entity.type = EntityType.TASK

    goal_entity = MagicMock()
    goal_entity.id = uuid.uuid4()
    goal_entity.type = EntityType.GOAL

    with patch(
        "src.inference.scorer.get_entities_via_edge", return_value=[task_entity, goal_entity]
    ):
        entity_ids = await _get_entities_for_person(db, org_id, person_id)

    assert len(entity_ids) == 1
    assert task_entity.id in entity_ids


@pytest.mark.asyncio
async def test_get_people_for_entities():
    """Should build a mapping from person_id to their owned entity_ids."""
    db = AsyncMock()
    org_id = uuid.uuid4()
    person1 = uuid.uuid4()
    entity1 = uuid.uuid4()
    entity2 = uuid.uuid4()

    edge1 = MagicMock()
    edge1.org_id = org_id
    edge1.from_entity_id = person1
    edge1.to_entity_id = entity1

    edge2 = MagicMock()
    edge2.org_id = org_id
    edge2.from_entity_id = person1
    edge2.to_entity_id = entity2

    with patch("src.inference.scorer.list_edges", side_effect=[[edge1], [edge2]]) as mock_fn:
        mapping = await _get_people_for_entities(db, org_id, [entity1, entity2])

    assert len(mapping[person1]) == 2
    # Verify org_id is passed to list_edges
    for call in mock_fn.call_args_list:
        assert call.kwargs["org_id"] == org_id


@pytest.mark.asyncio
async def test_score_delta_empty_entities():
    """score_delta with no changed entities should return empty dict."""
    db = AsyncMock()
    result = await score_delta(db, uuid.uuid4(), [])
    assert result == {}


@pytest.mark.asyncio
async def test_get_top_urgent_fallback_to_db():
    """When Redis cache is empty, should fall back to DB query."""
    db = AsyncMock()
    org_id = uuid.uuid4()
    person_id = uuid.uuid4()

    # Mock get_cached_scores to return empty (no Redis data)
    with patch("src.inference.scorer.get_cached_scores", return_value=[]):
        # Mock DB query
        mock_row = MagicMock()
        mock_row.entity_id = uuid.uuid4()
        mock_row.person_id = person_id
        mock_row.org_id = org_id
        mock_row.score = 85.0
        mock_row.score_components = {"test": 1}
        mock_row.goal_ids = []
        mock_row.provenance = []
        mock_row.computed_at = datetime.now(timezone.utc)

        result = MagicMock()
        result.scalars.return_value.all.return_value = [mock_row]
        db.execute.return_value = result

        scores = await get_top_urgent(db, org_id, person_id, RoleType.ENGINEER, limit=5)

    assert len(scores) == 1
    assert isinstance(scores[0], UrgencyScore)
    assert scores[0].score == 85.0
