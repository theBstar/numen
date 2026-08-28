"""Tests for MCP tool implementations."""

import json
from unittest.mock import patch

from src.mcp.tools import (
    get_entity_detail,
    list_tasks,
    search_by_source,
    search_entities,
)
from tests.conftest import TEST_ORG_ID, TEST_TASK_ID


@patch("src.mcp.tools.list_entities")
async def test_search_entities_returns_results(mock_list, mock_db, mock_entity):
    mock_list.return_value = [mock_entity]
    result = json.loads(await search_entities(mock_db, TEST_ORG_ID, "fix"))
    assert len(result) == 1
    assert result[0]["name"] == "TEST-1: Fix the bug"


@patch("src.mcp.tools.list_entities")
async def test_search_entities_invalid_type(mock_list, mock_db):
    result = json.loads(await search_entities(mock_db, TEST_ORG_ID, "test", "invalid_type"))
    assert "error" in result


@patch("src.mcp.tools.get_edges")
@patch("src.mcp.tools.get_entity")
async def test_get_entity_detail_found(mock_get, mock_edges, mock_db, mock_entity):
    mock_get.return_value = mock_entity
    mock_edges.return_value = []
    result = json.loads(await get_entity_detail(mock_db, TEST_ORG_ID, str(TEST_TASK_ID)))
    assert result["entity"]["name"] == "TEST-1: Fix the bug"
    assert result["edges"] == []


@patch("src.mcp.tools.get_entity")
async def test_get_entity_detail_not_found(mock_get, mock_db):
    mock_get.return_value = None
    result = json.loads(await get_entity_detail(mock_db, TEST_ORG_ID, str(TEST_TASK_ID)))
    assert "error" in result


async def test_get_entity_detail_invalid_uuid(mock_db):
    result = json.loads(await get_entity_detail(mock_db, TEST_ORG_ID, "not-a-uuid"))
    assert "error" in result


@patch("src.mcp.tools.list_entities")
async def test_list_tasks_filters_by_status(mock_list, mock_db, mock_entity):
    mock_list.return_value = [mock_entity]
    result = json.loads(await list_tasks(mock_db, TEST_ORG_ID, status="in_progress"))
    assert len(result) == 1

    result = json.loads(await list_tasks(mock_db, TEST_ORG_ID, status="done"))
    assert len(result) == 0


@patch("src.mcp.tools.get_entity_by_source")
async def test_search_by_source_found(mock_get, mock_db, mock_entity):
    mock_get.return_value = mock_entity
    result = json.loads(await search_by_source(mock_db, TEST_ORG_ID, "linear", "TEST-1"))
    assert result["name"] == "TEST-1: Fix the bug"


@patch("src.mcp.tools.get_entity_by_source")
async def test_search_by_source_not_found(mock_get, mock_db):
    mock_get.return_value = None
    result = json.loads(await search_by_source(mock_db, TEST_ORG_ID, "linear", "NONE"))
    assert "error" in result


async def test_search_by_source_invalid_source(mock_db):
    result = json.loads(await search_by_source(mock_db, TEST_ORG_ID, "unknown", "id"))
    assert "error" in result
