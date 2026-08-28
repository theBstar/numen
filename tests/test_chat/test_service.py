"""Tests for chat service - org_id scoping and security."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.chat.service import converse, delete_conversation, get_messages


@pytest.fixture
def org_id():
    return uuid.uuid4()


@pytest.fixture
def other_org_id():
    return uuid.uuid4()


@pytest.fixture
def conversation_id():
    return uuid.uuid4()


@pytest.mark.asyncio
async def test_get_messages_validates_org_id(org_id, other_org_id, conversation_id):
    """get_messages should return empty if conversation doesn't belong to org."""
    db = AsyncMock()

    # Simulate conversation not found for this org_id
    conv_result = MagicMock()
    conv_result.scalars.return_value.first.return_value = None
    db.execute.return_value = conv_result

    messages = await get_messages(db, conversation_id, other_org_id)
    assert messages == []


@pytest.mark.asyncio
async def test_get_messages_returns_messages_for_valid_org(org_id, conversation_id):
    """get_messages should return messages when conversation belongs to org."""
    db = AsyncMock()

    # Simulate conversation found
    mock_conv = MagicMock()
    mock_conv.org_id = org_id
    conv_result = MagicMock()
    conv_result.scalars.return_value.first.return_value = mock_conv

    # Simulate messages
    mock_msg = MagicMock()
    msgs_result = MagicMock()
    msgs_result.scalars.return_value.all.return_value = [mock_msg]

    db.execute.side_effect = [conv_result, msgs_result]

    messages = await get_messages(db, conversation_id, org_id)
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_delete_conversation_validates_org_id(org_id, other_org_id, conversation_id):
    """delete_conversation should do nothing if conversation doesn't belong to org."""
    db = AsyncMock()

    # Simulate conversation not found for this org_id
    conv_result = MagicMock()
    conv_result.scalars.return_value.first.return_value = None
    db.execute.return_value = conv_result

    await delete_conversation(db, conversation_id, other_org_id)

    # db.delete should never be called
    db.delete.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_delete_conversation_deletes_for_valid_org(org_id, conversation_id):
    """delete_conversation should delete when conversation belongs to org."""
    db = AsyncMock()

    # Simulate conversation found
    mock_conv = MagicMock()
    mock_conv.org_id = org_id

    # First call: find conversation for delete
    conv_result = MagicMock()
    conv_result.scalars.return_value.first.return_value = mock_conv

    # Second call: find conversation for get_messages validation
    conv_result2 = MagicMock()
    conv_result2.scalars.return_value.first.return_value = mock_conv

    # Third call: get messages (empty)
    msgs_result = MagicMock()
    msgs_result.scalars.return_value.all.return_value = []

    db.execute.side_effect = [conv_result, conv_result2, msgs_result]

    await delete_conversation(db, conversation_id, org_id)

    # Conversation should be deleted
    db.delete.assert_called_once_with(mock_conv)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_converse_loads_history_scoped_to_org(org_id, conversation_id):
    """History must never be loaded without the org scope.

    get_messages takes org_id with no default; omitting it once crashed
    every send before the agent even ran. It is also the tenant boundary.
    """
    db = AsyncMock()
    member = MagicMock()
    member.email = "someone@example.com"
    member.user_id = uuid.uuid4()
    member.id = uuid.uuid4()
    member.display_name = "Someone"

    async def _no_events(*_args, **_kwargs):
        return
        yield  # pragma: no cover

    with patch("src.chat.service.get_messages", new=AsyncMock(return_value=[])) as mock_get, patch(
        "src.chat.service.run_agent", new=_no_events
    ):
        async for _ in converse(db, org_id, member, conversation_id, "hello"):
            pass

    mock_get.assert_awaited_once_with(db, conversation_id, org_id)


@pytest.mark.asyncio
async def test_converse_persists_the_sanitized_reply(org_id, conversation_id):
    """What gets stored is the redacted text, not what streamed."""
    from src.agent.events import DoneEvent, SanitizedEvent, TokenEvent

    db = AsyncMock()
    conv_result = MagicMock()
    conv_result.scalars.return_value.first.return_value = None
    db.execute.return_value = conv_result

    member = MagicMock()
    member.email = "someone@example.com"
    member.user_id = uuid.uuid4()
    member.id = uuid.uuid4()
    member.display_name = "Someone"

    async def _events(*_args, **_kwargs):
        yield TokenEvent(content="key is sk-abcdefghijklmnop")
        yield SanitizedEvent(content="key is [redacted]")
        yield DoneEvent()

    with patch("src.chat.service.get_messages", new=AsyncMock(return_value=[])), patch(
        "src.chat.service.run_agent", new=_events
    ):
        seen = [e async for e in converse(db, org_id, member, conversation_id, "hi")]

    assert any(e.type.value == "sanitized" for e in seen)
    stored = [c.args[0] for c in db.add.call_args_list]
    assistant = [m for m in stored if getattr(m, "role", None) and m.role.value == "assistant"]
    assert assistant, "assistant reply should be persisted"
    assert assistant[0].content == "key is [redacted]"
