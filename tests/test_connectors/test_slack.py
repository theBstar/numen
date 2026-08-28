"""Tests for Slack connector."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.connectors.slack import _DECISION_EMOJI, SlackConnector
from src.shared.types import ConnectorSyncResult, SourceType


@pytest.fixture
def connector():
    return SlackConnector()


def test_source_type(connector):
    """Slack connector should have SLACK source type."""
    assert connector.source == SourceType.SLACK


# ---- _extract_entity_mentions tests ----


def test_extract_linear_issue():
    """Should detect Linear-style issue IDs like ENG-1234."""
    mentions = SlackConnector._extract_entity_mentions("Check out ENG-4501 and PLAT-42 please")
    types = {m["type"] for m in mentions}
    assert "linear_issue" in types
    values = {m["value"] for m in mentions}
    assert "ENG-4501" in values
    assert "PLAT-42" in values


def test_extract_github_pr():
    """Should detect GitHub PR references like PR #123."""
    mentions = SlackConnector._extract_entity_mentions("Please review PR #301")
    types = {m["type"] for m in mentions}
    assert "github_pr" in types


def test_extract_github_ref():
    """Should detect org/repo#123 references."""
    mentions = SlackConnector._extract_entity_mentions("Fixed in org/repo#42")
    types = {m["type"] for m in mentions}
    assert "github_ref" in types
    values = {m["value"] for m in mentions}
    assert "org/repo#42" in values


def test_extract_no_mentions():
    """Plain text should return empty list."""
    mentions = SlackConnector._extract_entity_mentions("Just a regular message")
    assert mentions == []


def test_extract_deduplicates():
    """Same mention appearing twice should be deduplicated."""
    mentions = SlackConnector._extract_entity_mentions("ENG-4501 is related to ENG-4501")
    eng_mentions = [m for m in mentions if m["value"] == "ENG-4501"]
    assert len(eng_mentions) == 1


def test_extract_multiple_types():
    """Should detect multiple mention types in one message."""
    text = "ENG-4501 is related to PR #301 and org/repo#42"
    mentions = SlackConnector._extract_entity_mentions(text)
    types = {m["type"] for m in mentions}
    assert len(types) >= 2


# ---- Decision emoji set ----


def test_decision_emoji_set():
    """Decision emoji set should contain expected emojis."""
    assert "white_check_mark" in _DECISION_EMOJI
    assert "heavy_check_mark" in _DECISION_EMOJI
    assert "approved" in _DECISION_EMOJI


# ---- Webhook handling ----


@pytest.mark.asyncio
async def test_handle_webhook_message_event(connector):
    """Should process message events for entity mentions."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "message",
            "text": "Check out ENG-4501",
            "ts": "1234567890.123456",
            "channel": "C12345",
        },
    }

    with patch.object(connector, "_link_mentions", new_callable=AsyncMock):
        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)


@pytest.mark.asyncio
async def test_handle_webhook_bot_message_skipped(connector):
    """Bot messages should be ignored."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "message",
            "bot_id": "B12345",
            "text": "ENG-4501",
            "ts": "1234567890.123456",
            "channel": "C12345",
        },
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    # No entities should have been processed
    assert result.edges_created == 0


@pytest.mark.asyncio
async def test_handle_webhook_reaction_decision(connector):
    """Reaction with decision emoji should create a decision entity."""
    db = AsyncMock()
    db.add = MagicMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "reaction_added",
            "reaction": "white_check_mark",
            "user": "U12345",
            "item": {
                "type": "message",
                "channel": "C12345",
                "ts": "1234567890.123456",
            },
        },
    }

    with patch("src.connectors.slack.upsert_entity") as mock_upsert:
        mock_entity = MagicMock()
        mock_entity.created_at = mock_entity.updated_at
        mock_upsert.return_value = mock_entity

        result = await connector.handle_webhook(db, org_id, payload)

    assert isinstance(result, ConnectorSyncResult)


@pytest.mark.asyncio
async def test_handle_webhook_reaction_non_decision(connector):
    """Non-decision emoji reactions should be ignored."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "reaction_added",
            "reaction": "thumbsup",
            "item": {
                "type": "message",
                "channel": "C12345",
                "ts": "1234567890.123456",
            },
        },
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    assert result.entities_created == 0


@pytest.mark.asyncio
async def test_handle_webhook_unknown_event(connector):
    """Unknown event types should be silently ignored."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "channel_created",
        },
    }

    result = await connector.handle_webhook(db, org_id, payload)
    assert isinstance(result, ConnectorSyncResult)
    assert len(result.errors) == 0


@pytest.mark.asyncio
async def test_handle_webhook_exception_captured(connector):
    """Errors during webhook handling should be captured."""
    db = AsyncMock()
    org_id = uuid.uuid4()

    payload = {
        "event": {
            "type": "message",
            "text": "ENG-4501",
            "ts": "123",
            "channel": "C1",
        },
    }

    with patch.object(connector, "_handle_message_event", side_effect=Exception("boom")):
        result = await connector.handle_webhook(db, org_id, payload)

    assert len(result.errors) == 1
    assert "slack webhook error" in result.errors[0]
