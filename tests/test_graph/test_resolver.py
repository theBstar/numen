"""Tests for cross-source entity resolution (FalkorDB-backed)."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.falkor_repository import GraphNode
from src.graph.resolver import (
    _enrich_entity,
    find_person,
    find_similar_persons,
    merge_entities,
    resolve_or_create_entity,
    resolve_or_create_person,
    resolve_person,
)
from src.shared.types import EntityCreate, EntityType, SourceType


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_falkor_node(
    *,
    entity_id=None,
    source_ids=None,
    canonical_name="Test",
    source="manual",
    entity_type="person",
    merged_into=None,
):
    """Create a mock FalkorDB node with .properties attribute."""
    eid = entity_id or str(uuid.uuid4())
    node = MagicMock()
    node.properties = {
        "id": eid,
        "org_id": "00000000-0000-0000-0000-000000000001",
        "type": entity_type,
        "source": source,
        "source_ids": json.dumps(source_ids or {}),
        "canonical_name": canonical_name,
        "properties": json.dumps({}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if merged_into is not None:
        node.properties["merged_into"] = str(merged_into)
    return node


def _mock_graph_result(nodes):
    """Create a mock graph.query result with result_set."""
    result = MagicMock()
    result.result_set = [[node] for node in nodes]
    return result


# ---- find_person tests ----


@pytest.mark.asyncio
async def test_find_person_by_email(org_id):
    """Should find existing person by email match in source_ids."""
    node = _make_falkor_node(
        source_ids={"email": "alice@test.com"},
        canonical_name="Alice",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"email": "alice@test.com", "name": "Alice"})

    assert person is not None
    assert person.source_ids["email"] == "alice@test.com"


@pytest.mark.asyncio
async def test_find_person_by_github_username(org_id):
    """Should find person by github_username when email doesn't match."""
    node = _make_falkor_node(
        source_ids={"github_username": "alice-gh"},
        canonical_name="Alice",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"github_username": "alice-gh", "name": "Alice"})

    assert person is not None
    assert person.source_ids["github_username"] == "alice-gh"


@pytest.mark.asyncio
async def test_find_person_by_github_key(org_id):
    """Should find person when github key is used instead of github_username."""
    node = _make_falkor_node(
        source_ids={"github": "dokafor"},
        canonical_name="dokafor",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"github_username": "dokafor"})

    assert person is not None
    assert person.source_ids["github"] == "dokafor"


@pytest.mark.asyncio
async def test_find_person_by_github_id(org_id):
    """Should find person by github_id (immutable numeric ID)."""
    node = _make_falkor_node(
        source_ids={"github_id": "12345678"},
        canonical_name="Alice",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"github_id": "12345678", "name": "Alice"})

    assert person is not None
    assert person.source_ids["github_id"] == "12345678"


@pytest.mark.asyncio
async def test_find_person_fallback_to_name(org_id):
    """Should find person by name when other identifiers don't match."""
    node = _make_falkor_node(
        source_ids={},
        canonical_name="Alice Test",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"name": "Alice Test"})

    assert person is not None
    assert person.canonical_name == "Alice Test"


@pytest.mark.asyncio
async def test_find_person_skips_merged_for_name(org_id):
    """Should not match merged entities by name."""
    node = _make_falkor_node(
        source_ids={},
        canonical_name="Alice Test",
        merged_into=uuid.uuid4(),
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"name": "Alice Test"})

    assert person is None


@pytest.mark.asyncio
async def test_find_person_no_match(org_id):
    """Should return None when no match found."""
    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"email": "notfound@test.com"})

    assert person is None


@pytest.mark.asyncio
async def test_find_person_email_priority_over_name(org_id):
    """Email match should take priority over name match."""
    email_node = _make_falkor_node(
        entity_id="email-entity",
        source_ids={"email": "alice@test.com"},
        canonical_name="Different Name",
    )
    name_node = _make_falkor_node(
        entity_id="name-entity",
        source_ids={},
        canonical_name="Alice",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([name_node, email_node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await find_person(None, org_id, {"email": "alice@test.com", "name": "Alice"})

    assert person is not None
    assert person.id == "email-entity"


# ---- resolve_person tests ----


@pytest.mark.asyncio
async def test_resolve_person_finds_existing(org_id):
    """Should find existing person and enrich it."""
    node = _make_falkor_node(
        source_ids={"email": "alice@test.com"},
        canonical_name="Alice",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        person = await resolve_person(None, org_id, {"email": "alice@test.com", "name": "Alice"})

    assert person is not None
    assert person.source_ids["email"] == "alice@test.com"


@pytest.mark.asyncio
async def test_resolve_person_creates_new(org_id):
    """Should create new person via upsert_entity when no match found."""
    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([])

    new_entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"email": "new@test.com"},
            "canonical_name": "New Person",
            "type": "person",
            "source": "manual",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity", return_value=new_entity) as mock_upsert,
    ):
        await resolve_person(None, org_id, {"email": "new@test.com", "name": "New Person"})

    mock_upsert.assert_called_once()


# ---- _enrich_entity tests ----


@pytest.mark.asyncio
async def test_enrich_entity_adds_new_ids(org_id):
    """Should add new identifiers to source_ids in FalkorDB."""
    entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"email": "alice@test.com"},
            "canonical_name": "Alice",
        }
    )

    mock_graph = AsyncMock()

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        enriched = await _enrich_entity(
            None, entity, {"email": "alice@test.com", "github_username": "alice-gh"}, org_id
        )

    assert enriched.source_ids["github_username"] == "alice-gh"
    mock_graph.query.assert_awaited_once()


@pytest.mark.asyncio
async def test_enrich_entity_no_update_needed(org_id):
    """Should not update FalkorDB if no new identifiers are added."""
    entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"email": "alice@test.com"},
            "canonical_name": "Alice",
        }
    )

    mock_graph = AsyncMock()

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        await _enrich_entity(None, entity, {"email": "alice@test.com"}, org_id)

    # No new info, so no graph query
    mock_graph.query.assert_not_awaited()


@pytest.mark.asyncio
async def test_enrich_entity_adds_github_id(org_id):
    """Should add github_id and github to source_ids."""
    entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"email": "alice@test.com"},
            "canonical_name": "Alice",
        }
    )

    mock_graph = AsyncMock()

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        enriched = await _enrich_entity(
            None, entity, {"github_id": "12345", "github": "alice-gh", "linear": "lin-123"}, org_id
        )

    assert enriched.source_ids["github_id"] == "12345"
    assert enriched.source_ids["github"] == "alice-gh"
    assert enriched.source_ids["linear"] == "lin-123"
    mock_graph.query.assert_awaited_once()


# ---- resolve_or_create_person tests ----


@pytest.mark.asyncio
async def test_resolve_or_create_person_email_match(org_id):
    """Cross-source email match should return the existing entity, NOT create a new one."""
    existing_id = str(uuid.uuid4())
    node = _make_falkor_node(
        entity_id=existing_id,
        source_ids={"email": "alice@test.com", "linear": "lin-123"},
        canonical_name="Alice",
        source="linear",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity") as mock_upsert,
    ):
        entity = await resolve_or_create_person(
            None,
            org_id,
            source=SourceType.GITHUB,
            source_ids={"github": "alice-gh", "email": "alice@test.com"},
            canonical_name="alice-gh",
            properties={"login": "alice-gh"},
        )

    # Cross-source match: must NOT create a new entity via upsert_entity.
    mock_upsert.assert_not_called()
    # Must return the existing entity (by id), enriched with the new github id.
    assert str(entity.id) == existing_id
    assert entity.source_ids.get("github") == "alice-gh"


@pytest.mark.asyncio
async def test_resolve_or_create_person_no_match_creates(org_id):
    """Should create new person when no cross-source match found."""
    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([])

    new_entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"github": "newuser"},
            "canonical_name": "newuser",
            "type": "person",
            "source": "github",
        }
    )

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity", return_value=new_entity) as mock_upsert,
    ):
        await resolve_or_create_person(
            None,
            org_id,
            source=SourceType.GITHUB,
            source_ids={"github": "newuser"},
            canonical_name="newuser",
            properties={"login": "newuser"},
        )

    mock_upsert.assert_called()


@pytest.mark.asyncio
async def test_resolve_or_create_person_no_strong_id_skips_resolution(org_id):
    """When only name is available, should skip resolution and just upsert."""
    new_entity = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"linear": "lin-999"},
            "canonical_name": "John Doe",
            "type": "person",
            "source": "linear",
        }
    )

    with patch("src.graph.resolver.upsert_entity", return_value=new_entity) as mock_upsert:
        await resolve_or_create_person(
            None,
            org_id,
            source=SourceType.LINEAR,
            source_ids={"linear": "lin-999"},
            canonical_name="John Doe",
            properties={"display_name": "John"},
        )

    mock_upsert.assert_called_once()


# ---- find_similar_persons tests ----


@pytest.mark.asyncio
async def test_find_similar_persons(org_id):
    """Should return similar person entities."""
    node1 = _make_falkor_node(canonical_name="Alice Smith")
    node2 = _make_falkor_node(canonical_name="Alice Jones")

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node1, node2])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        similar = await find_similar_persons(None, org_id, "Alice")

    assert len(similar) == 2


@pytest.mark.asyncio
async def test_find_similar_persons_no_criteria(org_id):
    """Should return empty when no name or email provided."""
    result = await find_similar_persons(None, org_id, "")
    assert result == []


# ---- merge_entities tests ----


@pytest.mark.asyncio
async def test_merge_entities_success(org_id):
    """Should merge source_ids, namespace duplicate properties, and mark as merged."""
    primary_id = uuid.uuid4()
    duplicate_id = uuid.uuid4()

    primary = GraphNode(
        {
            "id": str(primary_id),
            "org_id": str(org_id),
            "type": "person",
            "source": "manual",
            "source_ids": {"email": "alice@test.com"},
            "canonical_name": "Alice",
            "properties": {"team": "Platform"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    duplicate = GraphNode(
        {
            "id": str(duplicate_id),
            "org_id": str(org_id),
            "type": "person",
            "source": "github",
            "source_ids": {"github_username": "alice-gh"},
            "canonical_name": "alice-gh",
            "properties": {"github_url": "https://github.com/alice"},
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    merged_primary = GraphNode(
        {
            "id": str(primary_id),
            "org_id": str(org_id),
            "type": "person",
            "source": "manual",
            "source_ids": {"email": "alice@test.com", "github_username": "alice-gh"},
            "canonical_name": "Alice",
            "properties": {
                "team": "Platform",
                "_connector_data": {"github": {"github_url": "https://github.com/alice"}},
            },
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
    )

    mock_graph = AsyncMock()
    db = AsyncMock()

    with (
        patch("src.graph.resolver.get_entity", side_effect=[primary, duplicate, merged_primary]),
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.get_edges", return_value=[]),
    ):
        result = await merge_entities(db, primary_id, duplicate_id, org_id=org_id)

    assert result.source_ids["email"] == "alice@test.com"
    assert result.source_ids["github_username"] == "alice-gh"
    assert result.canonical_name == "Alice"
    # FalkorDB graph.query should have been called for update + merged_into
    assert mock_graph.query.await_count == 2


@pytest.mark.asyncio
async def test_merge_entities_not_found(org_id):
    """Should raise ValueError if primary or duplicate not found."""
    with patch("src.graph.resolver.get_entity", return_value=None):
        with pytest.raises(ValueError, match="Both primary and duplicate"):
            await merge_entities(AsyncMock(), uuid.uuid4(), uuid.uuid4(), org_id=org_id)


# ---- display-name vs handle scenario ----


@pytest.mark.asyncio
async def test_find_person_cross_source_github_match(org_id):
    """The key bug scenario: existing 'Dana Okafor' with email should be found
    when GitHub sync provides github username 'dokafor' with same email."""
    dana_node = _make_falkor_node(
        entity_id="dana-entity",
        source_ids={"email": "dana@test.com", "slack_id": "U123"},
        canonical_name="Dana Okafor",
        source="slack",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([dana_node])

    with patch("src.graph.resolver.get_org_graph", return_value=mock_graph):
        # GitHub sync would call with these identifiers
        person = await find_person(
            None,
            org_id,
            {
                "email": "dana@test.com",
                "github_username": "dokafor",
                "github_id": "12345678",
                "name": "dokafor",
            },
        )

    # Should match on email, not create a duplicate
    assert person is not None
    assert person.id == "dana-entity"
    assert person.canonical_name == "Dana Okafor"


# ---- resolve_or_create_entity (generic) tests ----


@pytest.mark.asyncio
async def test_resolve_or_create_entity_matches_task_by_linear_id(org_id):
    """A Linear task synced twice (same linear id) should resolve to the same entity, not duplicate."""
    existing_id = str(uuid.uuid4())
    node = _make_falkor_node(
        entity_id=existing_id,
        source_ids={"linear": "lin-123", "linear_identifier": "ENG-42"},
        canonical_name="ENG-42: Fix the thing",
        source="linear",
        entity_type="task",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity") as mock_upsert,
    ):
        result = await resolve_or_create_entity(
            None,
            EntityCreate(
                org_id=org_id,
                type=EntityType.TASK,
                source=SourceType.LINEAR,
                source_ids={"linear": "lin-123", "linear_identifier": "ENG-42"},
                canonical_name="ENG-42: Fix the thing (updated)",
                properties={"title": "Fix the thing", "state": "in_progress"},
            ),
        )

    mock_upsert.assert_not_called()
    assert str(result.id) == existing_id


@pytest.mark.asyncio
async def test_resolve_or_create_entity_task_no_match_creates(org_id):
    """A never-before-seen task should fall through to upsert_entity."""
    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([])

    created = GraphNode(
        {
            "id": str(uuid.uuid4()),
            "source_ids": {"linear": "lin-999"},
            "canonical_name": "NEW-1: New task",
            "type": "task",
            "source": "linear",
        }
    )

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity", return_value=created) as mock_upsert,
    ):
        result = await resolve_or_create_entity(
            None,
            EntityCreate(
                org_id=org_id,
                type=EntityType.TASK,
                source=SourceType.LINEAR,
                source_ids={"linear": "lin-999"},
                canonical_name="NEW-1: New task",
                properties={},
            ),
        )

    mock_upsert.assert_called_once()
    assert result is created


@pytest.mark.asyncio
async def test_resolve_or_create_entity_person_cross_source_returns_existing(org_id):
    """PERSON matched cross-source (by github_id) must return the existing entity, not create."""
    existing_id = str(uuid.uuid4())
    node = _make_falkor_node(
        entity_id=existing_id,
        source_ids={"email": "dana@test.com", "github_id": "12345"},
        canonical_name="Dana Okafor",
        source="manual",
    )

    mock_graph = AsyncMock()
    mock_graph.query.return_value = _mock_graph_result([node])

    with (
        patch("src.graph.resolver.get_org_graph", return_value=mock_graph),
        patch("src.graph.resolver.upsert_entity") as mock_upsert,
    ):
        result = await resolve_or_create_entity(
            None,
            EntityCreate(
                org_id=org_id,
                type=EntityType.PERSON,
                source=SourceType.GITHUB,
                source_ids={"github": "dokafor", "github_id": "12345"},
                canonical_name="dokafor",
                properties={"login": "dokafor"},
            ),
        )

    mock_upsert.assert_not_called()
    assert str(result.id) == existing_id
    # Should be enriched with the GitHub identifiers.
    assert result.source_ids.get("github_id") == "12345"
    assert result.source_ids.get("github") == "dokafor"
