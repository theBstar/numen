"""Tests for routing Slack events into the agent."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.principal import Audience, Principal, Surface
from src.slack.handler import handle_slack_event, should_handle

ORG_ID = uuid.uuid4()


def _principal(audience=Audience.PRIVATE):
    return Principal(
        org_id=ORG_ID,
        user_id=uuid.uuid4(),
        email="ada@example.com",
        surface=Surface.SLACK,
        audience=audience,
        member_id=uuid.uuid4(),
    )


# ── Which events are ours ─────────────────────────────────────────────


def test_handles_direct_message():
    assert should_handle({"type": "message", "channel_type": "im", "user": "U1", "text": "hi"})


def test_handles_app_mention():
    assert should_handle({"type": "app_mention", "user": "U1", "text": "<@U0> hi"})


def test_ignores_messages_from_bots():
    """Without this the agent answers itself, forever."""
    assert not should_handle({"type": "message", "channel_type": "im", "bot_id": "B1", "text": "hi"})
    assert not should_handle({"type": "message", "channel_type": "im", "user": "U1", "subtype": "bot_message"})


def test_ignores_its_own_edits_and_joins():
    assert not should_handle({"type": "message", "channel_type": "im", "subtype": "message_changed"})
    assert not should_handle({"type": "message", "channel_type": "im", "subtype": "channel_join"})


def test_ignores_channel_chatter_without_a_mention():
    """A message in a channel is only ours if we were addressed."""
    assert not should_handle({"type": "message", "channel_type": "channel", "user": "U1", "text": "standup at 10"})


def test_ignores_empty_text():
    assert not should_handle({"type": "message", "channel_type": "im", "user": "U1", "text": "   "})


# ── Routing ───────────────────────────────────────────────────────────


@pytest.fixture
def slack_calls():
    calls = {"posted": [], "ephemeral": [], "status": []}

    async def _post(_token, channel, text, thread_ts=None, blocks=None):
        calls["posted"].append({"channel": channel, "text": text, "thread_ts": thread_ts})
        return {"ok": True}

    async def _ephemeral(_token, channel, user, text, thread_ts=None):
        calls["ephemeral"].append({"channel": channel, "user": user, "text": text})
        return {"ok": True}

    async def _status(_token, channel, thread_ts, status):
        calls["status"].append(status)
        return {"ok": True}

    with patch("src.slack.handler.post_message", new=_post), patch(
        "src.slack.handler.post_ephemeral", new=_ephemeral
    ), patch("src.slack.handler.set_status", new=_status), patch(
        "src.slack.handler.get_bot_token", new=AsyncMock(return_value="xoxb-test")
    ):
        yield calls


async def _run(event, principal=_principal(), answer="Three tasks close Friday."):
    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    with patch("src.slack.handler.principal_for_slack_user", new=AsyncMock(return_value=principal)), patch(
        "src.slack.handler.get_or_create_external_conversation", new=AsyncMock(return_value=conversation)
    ), patch("src.slack.handler.answer_in_thread", new=AsyncMock(return_value=answer)):
        await handle_slack_event(AsyncMock(), ORG_ID, event)


@pytest.mark.asyncio
async def test_direct_message_gets_a_threaded_reply(slack_calls):
    await _run(
        {
            "type": "message",
            "channel_type": "im",
            "user": "U1",
            "text": "what is due?",
            "ts": "111.1",
            "channel": "D1",
        }
    )

    assert slack_calls["posted"], "expected a reply"
    reply = slack_calls["posted"][0]
    assert reply["channel"] == "D1"
    assert reply["thread_ts"] == "111.1"
    assert "Three tasks" in reply["text"]


@pytest.mark.asyncio
async def test_reply_joins_an_existing_thread(slack_calls):
    """Follow-ups stay in the thread rather than starting a new one."""
    await _run(
        {
            "type": "app_mention",
            "user": "U1",
            "text": "<@U0> and next week?",
            "ts": "222.2",
            "thread_ts": "111.1",
            "channel": "C1",
        }
    )

    assert slack_calls["posted"][0]["thread_ts"] == "111.1"


@pytest.mark.asyncio
async def test_status_is_set_while_working(slack_calls):
    await _run({"type": "message", "channel_type": "im", "user": "U1", "text": "hi", "ts": "1.1", "channel": "D1"})
    assert slack_calls["status"], "expected a working status"


@pytest.mark.asyncio
async def test_unknown_user_is_told_privately(slack_calls):
    """Someone without a Numen account gets an ephemeral note, not silence."""
    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    with patch("src.slack.handler.principal_for_slack_user", new=AsyncMock(return_value=None)), patch(
        "src.slack.handler.get_or_create_external_conversation", new=AsyncMock(return_value=conversation)
    ):
        await handle_slack_event(
            AsyncMock(),
            ORG_ID,
            {"type": "app_mention", "user": "U9", "text": "<@U0> hi", "ts": "1.1", "channel": "C1"},
        )

    assert slack_calls["ephemeral"], "expected a private explanation"
    assert not slack_calls["posted"], "must not post publicly for an unknown user"


@pytest.mark.asyncio
async def test_channel_mention_resolves_a_shared_audience(slack_calls):
    captured = {}

    async def _capture(_db, _org, *, slack_user_id, is_direct_message):
        captured["dm"] = is_direct_message
        return _principal(Audience.SHARED)

    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    with patch("src.slack.handler.principal_for_slack_user", new=_capture), patch(
        "src.slack.handler.get_or_create_external_conversation", new=AsyncMock(return_value=conversation)
    ), patch("src.slack.handler.answer_in_thread", new=AsyncMock(return_value="ok")):
        await handle_slack_event(
            AsyncMock(),
            ORG_ID,
            {"type": "app_mention", "user": "U1", "text": "<@U0> hi", "ts": "1.1", "channel": "C1"},
        )

    assert captured["dm"] is False


@pytest.mark.asyncio
async def test_mention_markup_is_stripped_before_asking(slack_calls):
    captured = {}

    async def _answer(_db, _principal, _conversation_id, text, **_kwargs):
        captured["text"] = text
        return "ok"

    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    with patch("src.slack.handler.principal_for_slack_user", new=AsyncMock(return_value=_principal())), patch(
        "src.slack.handler.get_or_create_external_conversation", new=AsyncMock(return_value=conversation)
    ), patch("src.slack.handler.answer_in_thread", new=_answer):
        await handle_slack_event(
            AsyncMock(),
            ORG_ID,
            {"type": "app_mention", "user": "U1", "text": "<@U0BOT> what is due?", "ts": "1.1", "channel": "C1"},
        )

    assert captured["text"] == "what is due?"


@pytest.mark.asyncio
async def test_agent_failure_still_replies(slack_calls):
    """Silence reads as a broken bot; say something instead."""
    conversation = MagicMock()
    conversation.id = uuid.uuid4()

    with patch("src.slack.handler.principal_for_slack_user", new=AsyncMock(return_value=_principal())), patch(
        "src.slack.handler.get_or_create_external_conversation", new=AsyncMock(return_value=conversation)
    ), patch("src.slack.handler.answer_in_thread", new=AsyncMock(side_effect=RuntimeError("model down"))):
        await handle_slack_event(
            AsyncMock(),
            ORG_ID,
            {"type": "message", "channel_type": "im", "user": "U1", "text": "hi", "ts": "1.1", "channel": "D1"},
        )

    assert slack_calls["posted"], "expected an apology rather than silence"
    assert "model down" not in slack_calls["posted"][0]["text"]
