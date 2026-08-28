"""Tests for GitHub connector."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.github import GitHubConnector
from src.shared.types import ConnectorSyncResult, SourceType


@pytest.fixture
def connector():
    return GitHubConnector()


def test_source_type(connector):
    """GitHub connector should have GITHUB source type."""
    assert connector.source == SourceType.GITHUB


@pytest.mark.asyncio
async def test_handle_webhook_pr_event(connector):
    """Should process PR webhook events."""
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "title": "Fix auth flow",
            "state": "open",
            "merged": False,
            "user": {"login": "alice"},
            "html_url": "https://github.com/org/repo/pull/42",
        },
        "repository": {"full_name": "org/repo"},
    }

    with patch("src.connectors.github.upsert_entity") as mock_upsert:
        mock_entity = MagicMock()
        mock_entity.created_at = mock_entity.updated_at
        mock_upsert.return_value = mock_entity

        with patch("src.connectors.github.get_entity_by_source", return_value=None):
            result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)
    assert result.source == SourceType.GITHUB


@pytest.mark.asyncio
async def test_handle_webhook_push_event(connector):
    """Should process push webhook events."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    mock_person = MagicMock()
    mock_person.properties = {"recent_pushes": []}

    payload = {
        "action": "push",
        "sender": {"login": "alice"},
        "repository": {"full_name": "org/repo"},
        "ref": "refs/heads/main",
        "after": "abc123def456",
        "commits": [{"id": "c1"}, {"id": "c2"}],
    }

    with patch("src.connectors.github.get_entity_by_source", return_value=mock_person):
        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)


@pytest.mark.asyncio
async def test_handle_webhook_push_no_sender(connector):
    """Push without sender should be a no-op."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "push",
        "sender": {},  # No login
        "commits": [{"id": "c1"}],
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    assert result.entities_updated == 0


@pytest.mark.asyncio
async def test_handle_webhook_unknown_event(connector):
    """Unknown event types should be silently ignored."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "ping",
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_handle_webhook_exception(connector):
    """Errors during webhook handling should be captured."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "pull_request": {},  # Incomplete payload
    }

    with patch("src.connectors.github.upsert_entity", side_effect=KeyError("number")):
        result = await connector.handle_webhook(db, org_id, payload)

    assert len(result.errors) == 1


@pytest.mark.asyncio
async def test_paginate_single_page(connector):
    """Pagination with no Link header should return single page."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [{"id": 1}, {"id": 2}]
    mock_response.headers = {}  # No Link header
    mock_client.get.return_value = mock_response

    items = []
    async for item in GitHubConnector._paginate(mock_client, "https://api.github.com/test"):
        items.append(item)

    assert len(items) == 2


@pytest.mark.asyncio
async def test_paginate_non_list_response(connector):
    """Non-list response should stop pagination."""
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"message": "Not a list"}
    mock_response.headers = {}
    mock_client.get.return_value = mock_response

    items = []
    async for item in GitHubConnector._paginate(mock_client, "https://api.github.com/test"):
        items.append(item)

    assert len(items) == 0
