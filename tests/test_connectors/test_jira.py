"""Tests for Jira connector."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.jira import JiraConnector, _adf_to_text, _api_base, _cloud_id
from src.shared.types import ConnectorSyncResult, SourceType


@pytest.fixture
def connector():
    return JiraConnector()


def test_source_type(connector):
    assert connector.source == SourceType.JIRA


def test_cloud_id_prefers_workspace_id():
    token = MagicMock()
    token.settings = {"workspace_id": "abc-123"}
    assert _cloud_id(token) == "abc-123"


def test_cloud_id_falls_back_to_cloud_id_key():
    token = MagicMock()
    token.settings = {"cloud_id": "xyz-789"}
    assert _cloud_id(token) == "xyz-789"


def test_api_base_raises_when_missing_cloud_id():
    token = MagicMock()
    token.settings = {}
    with pytest.raises(RuntimeError, match="missing cloud_id"):
        _api_base(token)


def test_api_base_uses_atlassian_ex_url():
    token = MagicMock()
    token.settings = {"workspace_id": "abc-123"}
    assert _api_base(token) == "https://api.atlassian.com/ex/jira/abc-123/rest/api/3"


def test_adf_to_text_extracts_plain_text():
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ],
            }
        ],
    }
    assert _adf_to_text(adf) == "Hello world"


def test_adf_to_text_handles_none_and_strings():
    assert _adf_to_text(None) is None
    assert _adf_to_text("plain") == "plain"


@pytest.mark.asyncio
async def test_handle_webhook_issue_updated_calls_upsert(connector):
    db = AsyncMock()
    org_id = uuid.uuid4()
    payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "id": "10001",
            "key": "ENG-1",
            "fields": {
                "summary": "Webhook update",
                "status": {"name": "In Progress", "statusCategory": {"key": "indeterminate"}},
                "project": {"id": "1", "key": "ENG", "name": "Engineering"},
                "assignee": None,
                "reporter": None,
                "labels": [],
                "components": [],
                "issuelinks": [],
                "created": "2026-04-30T00:00:00.000+0000",
                "updated": "2026-04-30T00:00:00.000+0000",
            },
        },
    }

    with patch("src.connectors.jira.resolve_or_create_entity") as mock_resolve:
        entity = MagicMock()
        entity.created_at = entity.updated_at
        mock_resolve.return_value = entity
        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)
    assert result.source == SourceType.JIRA
    assert result.entities_created == 1
    mock_resolve.assert_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_unknown_event_is_ignored(connector):
    db = AsyncMock()
    org_id = uuid.uuid4()
    payload = {"webhookEvent": "jira:something_else", "issue": {}}
    result = await connector.handle_webhook(db, org_id, payload)
    assert result.entities_created == 0
    assert result.entities_updated == 0
    assert result.errors == []
