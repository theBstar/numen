"""Tests for event handlers."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.events.handlers import (
    on_briefing_scoring,
    on_edge_task_transitions,
    on_pr_author_link,
    on_pr_auto_link,
    on_pr_task_transitions,
    on_sync_link_suggestions,
    on_sync_person_detection,
)
from src.events.types import BriefingRequested, EdgeCreated, EntityUpserted, SyncCompleted
from src.shared.types import ConnectorSyncResult, EdgeType, EntityType, SourceType


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def db():
    return AsyncMock()


# ── on_pr_task_transitions ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_pr_task_transitions_calls_propagate(db, org_id):
    """Should call propagate_pr_state_to_tasks for COMMIT_PR entities."""
    entity_id = uuid.uuid4()
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=entity_id,
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=False,
        properties={"state": "open"},
    )
    mock_propagate = AsyncMock()
    with patch("src.graph.task_transitions.propagate_pr_state_to_tasks", mock_propagate):
        await on_pr_task_transitions(event)
    mock_propagate.assert_awaited_once_with(db, entity_id)


@pytest.mark.asyncio
async def test_pr_task_transitions_skips_non_pr(db, org_id):
    """Should not call propagate for non-COMMIT_PR entities."""
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.TASK,
        source=SourceType.LINEAR,
        was_created=True,
        properties={},
    )
    # Should not raise or call anything
    await on_pr_task_transitions(event)


# ── on_pr_auto_link ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_link_skips_non_pr(db, org_id):
    """Should not try to link non-PR entities."""
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.TASK,
        source=SourceType.LINEAR,
        was_created=True,
        properties={},
    )
    await on_pr_auto_link(event)


@pytest.mark.asyncio
async def test_auto_link_extracts_identifier(db, org_id):
    """Should extract ENG-123 from PR title and create SHIPS_TO edge."""
    task_entity = MagicMock()
    task_entity.id = uuid.uuid4()
    task_entity.type = EntityType.TASK

    entity_id = uuid.uuid4()
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=entity_id,
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={"title": "fix: ENG-123 add auth flow", "head_branch": "feat/eng-123"},
    )

    with (
        patch("src.graph.get_entity_by_source", new_callable=AsyncMock, return_value=task_entity) as mock_get,
        patch("src.graph.upsert_edge", new_callable=AsyncMock) as mock_edge,
    ):
        await on_pr_auto_link(event)

    mock_get.assert_awaited()
    mock_edge.assert_awaited()


@pytest.mark.asyncio
async def test_auto_link_no_identifiers(db, org_id):
    """Should do nothing if no task identifiers in title/branch."""
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={"title": "fix typo in readme", "branch": "fix-typo"},
    )
    # Should not raise
    await on_pr_auto_link(event)


# ── on_pr_author_link ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_author_link_skips_non_pr(db, org_id):
    """Should not try to link author for non-PR entities."""
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.TASK,
        source=SourceType.LINEAR,
        was_created=True,
        properties={},
    )
    await on_pr_author_link(event)


@pytest.mark.asyncio
async def test_author_link_skips_no_author(db, org_id):
    """Should do nothing if properties has no author."""
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={"title": "PR title"},
    )
    await on_pr_author_link(event)


@pytest.mark.asyncio
async def test_author_link_creates_person_and_edge(db, org_id):
    """Should create person entity and AUTHORED edge."""
    person = MagicMock()
    person.id = uuid.uuid4()

    entity_id = uuid.uuid4()
    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=entity_id,
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={"author": "alice-gh"},
    )

    with (
        patch("src.graph.resolve_or_create_person", new_callable=AsyncMock, return_value=person),
        patch("src.graph.upsert_edge", new_callable=AsyncMock) as mock_edge,
    ):
        await on_pr_author_link(event)

    mock_edge.assert_awaited_once()


# ── on_sync_person_detection ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_person_detection(db, org_id):
    """Should call detect_person_duplicates."""
    result = ConnectorSyncResult(source=SourceType.GITHUB)
    event = SyncCompleted(db=db, org_id=org_id, source=SourceType.GITHUB, result=result)

    with patch("src.graph.resolution.detect_person_duplicates", new_callable=AsyncMock, return_value=[]) as mock:
        await on_sync_person_detection(event)
    mock.assert_awaited_once_with(db, org_id)


# ── on_sync_link_suggestions ────────────────────────────────────────


@pytest.mark.asyncio
async def test_sync_link_suggestions_skips_no_changes(db, org_id):
    """Should skip if no entities were created or updated."""
    result = ConnectorSyncResult(source=SourceType.LINEAR)
    result.entities_created = 0
    result.entities_updated = 0
    event = SyncCompleted(db=db, org_id=org_id, source=SourceType.LINEAR, result=result)

    await on_sync_link_suggestions(event)


@pytest.mark.asyncio
async def test_sync_link_suggestions_runs_when_entities_changed(db, org_id):
    """Should call suggest_pr_task_links when entities changed."""
    result = ConnectorSyncResult(source=SourceType.GITHUB)
    result.entities_created = 3
    event = SyncCompleted(db=db, org_id=org_id, source=SourceType.GITHUB, result=result)

    with patch("src.llm.link_suggester.suggest_pr_task_links", new_callable=AsyncMock, return_value=[]) as mock:
        await on_sync_link_suggestions(event)
    mock.assert_awaited_once_with(db, org_id)


# ── on_briefing_scoring ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_briefing_scoring(db, org_id):
    """Should call score_org."""
    event = BriefingRequested(db=db, org_id=org_id, member_id=uuid.uuid4())

    with patch("src.inference.scorer.score_org", new_callable=AsyncMock) as mock:
        await on_briefing_scoring(event)
    mock.assert_awaited_once_with(db, org_id)


# ── on_edge_task_transitions ───────────────────────────────────────


@pytest.mark.asyncio
async def test_edge_task_transitions_calls_propagate_for_ships_to(db, org_id):
    """Should call propagate_pr_state_to_tasks for both directions on SHIPS_TO."""
    from_id = uuid.uuid4()
    to_id = uuid.uuid4()
    event = EdgeCreated(
        db=db,
        org_id=org_id,
        from_entity_id=from_id,
        to_entity_id=to_id,
        edge_type=EdgeType.SHIPS_TO,
    )
    with patch("src.graph.task_transitions.propagate_pr_state_to_tasks", new_callable=AsyncMock) as mock:
        await on_edge_task_transitions(event)
    assert mock.await_count == 2
    mock.assert_any_await(db, from_id)
    mock.assert_any_await(db, to_id)


@pytest.mark.asyncio
async def test_edge_task_transitions_skips_non_ships_to(db, org_id):
    """Should not call propagate for non-SHIPS_TO edges."""
    event = EdgeCreated(
        db=db,
        org_id=org_id,
        from_entity_id=uuid.uuid4(),
        to_entity_id=uuid.uuid4(),
        edge_type=EdgeType.AUTHORED,
    )
    # Should not raise or call anything
    await on_edge_task_transitions(event)


# ── on_pr_auto_link with commit messages ───────────────────────────


@pytest.mark.asyncio
async def test_auto_link_extracts_identifier_from_branch(db, org_id):
    """Should extract ENG-456 from branch name when title has no identifier."""
    task_entity = MagicMock()
    task_entity.id = uuid.uuid4()
    task_entity.type = EntityType.TASK

    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={"title": "fix auth flow", "head_branch": "feat/ENG-456-auth"},
    )

    with (
        patch("src.graph.get_entity_by_source", new_callable=AsyncMock, return_value=task_entity),
        patch("src.graph.upsert_edge", new_callable=AsyncMock) as mock_edge,
    ):
        await on_pr_auto_link(event)

    mock_edge.assert_awaited()


@pytest.mark.asyncio
async def test_auto_link_extracts_identifier_from_commit_messages(db, org_id):
    """Should extract PLAT-99 from commit messages."""
    task_entity = MagicMock()
    task_entity.id = uuid.uuid4()
    task_entity.type = EntityType.TASK

    event = EntityUpserted(
        db=db,
        org_id=org_id,
        entity_id=uuid.uuid4(),
        entity_type=EntityType.COMMIT_PR,
        source=SourceType.GITHUB,
        was_created=True,
        properties={
            "title": "misc fixes",
            "head_branch": "fix-stuff",
            "commit_messages": ["PLAT-99 fix login redirect", "cleanup tests"],
        },
    )

    with (
        patch("src.graph.get_entity_by_source", new_callable=AsyncMock, return_value=task_entity),
        patch("src.graph.upsert_edge", new_callable=AsyncMock) as mock_edge,
    ):
        await on_pr_auto_link(event)

    mock_edge.assert_awaited()
