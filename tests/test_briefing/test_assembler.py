"""Tests for briefing assembler module."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.briefing.assembler import (
    _MAX_BRIEFING_ITEMS,
    _build_source_trace,
    _get_goal_tags_for_entity,
    _get_person_entity,
    _score_to_briefing_item,
    assemble_briefing,
)
from src.shared.types import (
    BriefingItem,
    EntityType,
    RoleType,
    SourceType,
    UrgencyScore,
)


@pytest.fixture
def org_id():
    return uuid.uuid4()


# ---- _get_person_entity tests ----


@pytest.mark.asyncio
async def test_get_person_entity_no_person_entity_id(org_id):
    """If member has no person_entity_id, should return None."""
    db = AsyncMock()
    member = MagicMock()
    member.person_entity_id = None

    result = await _get_person_entity(db, member, org_id)
    assert result is None


@pytest.mark.asyncio
async def test_get_person_entity_found(org_id):
    """Should return the Person entity when linked."""
    db = AsyncMock()
    member = MagicMock()
    member.person_entity_id = uuid.uuid4()

    mock_entity = MagicMock()
    mock_entity.type = EntityType.PERSON

    with patch("src.briefing.assembler.get_entity", return_value=mock_entity) as mock_get:
        result = await _get_person_entity(db, member, org_id)

    assert result == mock_entity
    mock_get.assert_called_once_with(db, member.person_entity_id, org_id=org_id)


@pytest.mark.asyncio
async def test_get_person_entity_passes_org_id(org_id):
    """_get_person_entity must pass org_id to get_entity."""
    db = AsyncMock()
    member = MagicMock()
    member.person_entity_id = uuid.uuid4()

    mock_entity = MagicMock()
    mock_entity.type = EntityType.PERSON

    with patch("src.briefing.assembler.get_entity", return_value=mock_entity) as mock_get:
        await _get_person_entity(db, member, org_id)

    mock_get.assert_called_once_with(db, member.person_entity_id, org_id=org_id)


# ---- _get_goal_tags_for_entity tests ----


@pytest.mark.asyncio
async def test_get_goal_tags_for_entity(org_id):
    """Should return goal names from TAGGED_TO edges."""
    db = AsyncMock()

    goal1 = MagicMock()
    goal1.canonical_name = "Retention +15%"
    goal2 = MagicMock()
    goal2.canonical_name = "Ship enterprise"

    with patch("src.briefing.assembler.get_entities_via_edge", return_value=[goal1, goal2]):
        tags = await _get_goal_tags_for_entity(db, uuid.uuid4(), org_id)

    assert "Retention +15%" in tags
    assert len(tags) == 2


@pytest.mark.asyncio
async def test_get_goal_tags_no_goals(org_id):
    """Entity with no goal tags returns empty list."""
    db = AsyncMock()

    with patch("src.briefing.assembler.get_entities_via_edge", return_value=[]):
        tags = await _get_goal_tags_for_entity(db, uuid.uuid4(), org_id)

    assert tags == []


@pytest.mark.asyncio
async def test_get_goal_tags_passes_org_id(org_id):
    """_get_goal_tags_for_entity must pass org_id to get_entities_via_edge."""
    db = AsyncMock()
    eid = uuid.uuid4()

    with patch("src.briefing.assembler.get_entities_via_edge", return_value=[]) as mock_fn:
        await _get_goal_tags_for_entity(db, eid, org_id)

    assert mock_fn.call_args.kwargs["org_id"] == org_id


# ---- _build_source_trace tests ----


def test_build_source_trace_with_url():
    """Should extract source URL from properties."""
    entity = MagicMock()
    entity.id = uuid.uuid4()
    entity.source = SourceType.GITHUB
    entity.canonical_name = "PR #42"
    entity.source_ids = {"github": "org/repo#42"}
    entity.properties = {"html_url": "https://github.com/org/repo/pull/42", "status": "open"}
    entity.updated_at = datetime.now(timezone.utc)

    trace = _build_source_trace(entity)
    assert trace.source == "github"
    assert trace.source_url == "https://github.com/org/repo/pull/42"
    assert trace.entity_name == "PR #42"


def test_build_source_trace_no_url():
    """If no URL in properties, source_url should be from source_ids or None."""
    entity = MagicMock()
    entity.id = uuid.uuid4()
    entity.source = SourceType.LINEAR
    entity.canonical_name = "ENG-1234"
    entity.source_ids = {"linear": "abc123"}
    entity.properties = {"status": "in_progress"}
    entity.updated_at = datetime.now(timezone.utc)

    trace = _build_source_trace(entity)
    assert trace.source_url is None


# ---- _score_to_briefing_item tests ----


def test_score_to_briefing_item():
    """Should convert UrgencyScore + entity into a BriefingItem."""
    entity = MagicMock()
    entity.id = uuid.uuid4()
    entity.type = EntityType.TASK
    entity.canonical_name = "ENG-4501: Fix bug"
    entity.source = SourceType.LINEAR
    entity.source_ids = {"linear": "abc"}
    entity.properties = {"status": "in_progress"}
    entity.updated_at = datetime.now(timezone.utc)

    score = UrgencyScore(
        entity_id=entity.id,
        person_id=uuid.uuid4(),
        org_id=uuid.uuid4(),
        score=75.5,
        components={},
        goal_ids=[],
        provenance=[],
        computed_at=datetime.now(timezone.utc),
    )

    item = _score_to_briefing_item(
        score=score,
        entity=entity,
        why="Blocking 3 items",
        goal_tags=["Retention"],
        source_links=[{"label": "linear", "url": "https://linear.app"}],
        suggested_action="Fix today",
    )

    assert isinstance(item, BriefingItem)
    assert item.title == "ENG-4501: Fix bug"
    assert item.why_it_matters == "Blocking 3 items"
    assert item.urgency_score == 75.5
    assert "Retention" in item.goal_tags


# ---- assemble_briefing tests ----


@pytest.mark.asyncio
async def test_assemble_briefing_no_person_entity():
    """Member with no person entity should return empty briefing."""
    db = AsyncMock()
    member = MagicMock()
    member.person_entity_id = None
    member.id = uuid.uuid4()
    member.org_id = uuid.uuid4()
    member.email = "nobody@test.com"

    items, empty_reason = await assemble_briefing(db, member)
    assert items == []
    assert empty_reason == "no_person_entity"


@pytest.mark.asyncio
async def test_assemble_briefing_max_items_cap():
    """Briefing should be capped at _MAX_BRIEFING_ITEMS."""
    assert _MAX_BRIEFING_ITEMS == 10


@pytest.mark.asyncio
async def test_assemble_briefing_engineer_produces_items():
    """An engineer with urgent tasks should get non-empty briefing items."""
    db = AsyncMock()
    org_id = uuid.uuid4()
    person_id = uuid.uuid4()
    entity_id = uuid.uuid4()

    member = MagicMock()
    member.person_entity_id = person_id
    member.org_id = org_id
    member.id = uuid.uuid4()
    member.email = "alice@test.com"
    member.role = RoleType.ENGINEER

    person_entity = MagicMock()
    person_entity.id = person_id
    person_entity.type = EntityType.PERSON

    task_entity = MagicMock()
    task_entity.id = entity_id
    task_entity.type = EntityType.TASK
    task_entity.canonical_name = "Fix auth flow"
    task_entity.source = SourceType.LINEAR
    task_entity.source_ids = {"linear": "ENG-123"}
    task_entity.properties = {"status": "in_progress", "html_url": "https://linear.app/t/ENG-123"}
    task_entity.updated_at = datetime.now(timezone.utc)

    score = UrgencyScore(
        entity_id=entity_id,
        person_id=person_id,
        org_id=org_id,
        score=85.0,
        components={"blocking_count": 2},
        goal_ids=[],
        provenance=[],
        computed_at=datetime.now(timezone.utc),
    )

    with (
        patch("src.briefing.assembler.get_entity", return_value=task_entity),
        patch("src.briefing.assembler.get_entities_via_edge", return_value=[]),
        patch("src.briefing.assembler.count_edges", return_value=0),
        patch("src.briefing.assembler.list_edges", return_value=[]),
        patch("src.briefing.assembler.get_top_urgent", return_value=[score]),
    ):
        # Mock _get_person_entity to return person_entity
        with patch("src.briefing.assembler._get_person_entity", return_value=person_entity):
            items, empty_reason = await assemble_briefing(db, member)

    assert len(items) >= 1
    assert items[0].title == "Fix auth flow"
    assert items[0].urgency_score == 85.0
    assert empty_reason is None
