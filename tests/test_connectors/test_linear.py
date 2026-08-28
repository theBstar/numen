"""Tests for Linear connector."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.linear import LinearConnector
from src.shared.types import ConnectorSyncResult, SourceType


@pytest.fixture
def connector():
    return LinearConnector()


def test_source_type(connector):
    """Linear connector should have LINEAR source type."""
    assert connector.source == SourceType.LINEAR


@pytest.mark.asyncio
async def test_execute_graphql_success(connector):
    """Should return data dict on successful GraphQL response."""
    from src.connectors import linear as linear_mod
    linear_mod._LIMITER._next_allowed_at = 0.0
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "data": {
            "users": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [
                    {"id": "user-1", "name": "Alice", "email": "alice@test.com"},
                ],
            }
        }
    }
    mock_client.request.return_value = mock_response

    data = await LinearConnector._execute_graphql(mock_client, "query { users { nodes { id } } }")

    assert "users" in data
    assert len(data["users"]["nodes"]) == 1
    mock_client.request.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_graphql_error(connector):
    """Should raise RuntimeError on GraphQL errors."""
    from src.connectors import linear as linear_mod
    linear_mod._LIMITER._next_allowed_at = 0.0
    mock_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "errors": [{"message": "Unauthorized"}],
    }
    mock_client.request.return_value = mock_response

    with pytest.raises(RuntimeError, match="Linear GraphQL errors"):
        await LinearConnector._execute_graphql(mock_client, "query { bad }")


@pytest.mark.asyncio
async def test_handle_webhook_issue_create(connector):
    """Should process issue create webhook events."""
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "create",
        "type": "Issue",
        "data": {
            "id": "issue-abc",
            "identifier": "ENG-9999",
            "title": "New issue from webhook",
            "priority": 2,
            "state": {"name": "Todo", "type": "unstarted"},
        },
    }

    with patch("src.connectors.linear.upsert_entity") as mock_upsert:
        mock_entity = MagicMock()
        mock_entity.created_at = mock_entity.updated_at  # Simulate new entity
        mock_upsert.return_value = mock_entity

        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)
    assert result.source == SourceType.LINEAR


@pytest.mark.asyncio
async def test_handle_webhook_comment_no_issue():
    """Should handle comment webhook when issue entity is not found."""
    connector = LinearConnector()
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "create",
        "type": "Comment",
        "data": {
            "id": "comment-1",
            "issueId": "issue-not-found",
            "body": "This is a comment",
        },
    }

    with patch("src.graph.get_entity_by_source", return_value=None):
        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_handle_webhook_unknown_type(connector):
    """Should silently ignore unknown webhook event types."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "create",
        "type": "UnknownType",
        "data": {},
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_handle_webhook_exception_captured(connector):
    """Errors during webhook handling should be captured in result.errors."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "action": "create",
        "type": "Issue",
        "data": {},  # Missing required fields will cause an error
    }

    with patch("src.connectors.linear.upsert_entity", side_effect=KeyError("id")):
        result = await connector.handle_webhook(db, org_id, payload)

    assert len(result.errors) == 1
    assert "linear webhook error" in result.errors[0]
