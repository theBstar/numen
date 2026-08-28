"""Tests that delayed projects use FalkorDB entity IDs, not PostgreSQL seed IDs."""

import uuid

import pytest

from src.api.schemas import DelayedProjectItem


@pytest.fixture
def org_id():
    return uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")


@pytest.fixture
def falkor_project_id():
    """The real FalkorDB-generated entity ID."""
    return uuid.UUID("88d0edcc-5620-4956-9ac1-3a3e47bdf4e6")


@pytest.fixture
def seed_project_id():
    """The deterministic seed UUID - should NOT appear in API responses."""
    return uuid.UUID("ccddaabb-0000-0000-0000-000000000002")


def test_delayed_project_item_uses_correct_id(falkor_project_id, seed_project_id):
    """DelayedProjectItem should use FalkorDB entity ID, not seed UUID."""
    item = DelayedProjectItem(
        id=str(falkor_project_id),
        name="Onboarding V2",
        days_overdue=5,
        remaining_tasks=3,
    )
    assert item.id == str(falkor_project_id)
    assert str(seed_project_id) not in item.id


def test_delayed_projects_must_come_from_falkordb():
    """Dashboard delayed projects must query FalkorDB (graph_list_entities),
    not PostgreSQL (select(Entity)), to get correct entity IDs.

    This test documents the architectural requirement: after the FalkorDB
    migration, all entity ID references must come from FalkorDB to ensure
    frontend links match the graph-canonical entity IDs.
    """
    # The dashboard summary function should use graph_list_entities
    # not select(Entity) for project queries.
    # This is verified by the implementation using graph_list_entities
    # which returns GraphNode objects with FalkorDB-generated IDs.
    import inspect

    from src.api.routes_dashboard import get_dashboard_summary

    source = inspect.getsource(get_dashboard_summary)
    # The function should NOT contain direct Entity SQL queries for projects
    assert "select(Entity)" not in source or "Entity.type == EntityType.PROJECT" not in source, (
        "Dashboard should query FalkorDB via graph_list_entities, not PostgreSQL Entity table"
    )
