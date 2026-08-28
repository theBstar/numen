"""Tests for making a briefing item actionable rather than a dead end."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.principal import Audience, Principal, Surface
from src.briefing.slack_delivery import _build_blocks
from src.shared.types import BriefingItem, EntityType
from src.slack.actions import ACTION_ASK, ACTION_LESS, ACTION_SNOOZE, handle_block_action


def _item(title="Close the payments PRD", entity_id=None):
    return BriefingItem(
        entity_id=entity_id or uuid.uuid4(),
        entity_type=EntityType.TASK,
        title=title,
        why_it_matters="Blocks two engineers on Monday.",
        urgency_score=0.82,
        source_links=[{"url": "https://example.com/t/1", "label": "Linear"}],
    )


def _member():
    member = MagicMock()
    member.id = uuid.uuid4()
    member.email = "ada@example.com"
    member.display_name = "Ada"
    return member


# ── Rendering ─────────────────────────────────────────────────────────


def test_each_item_offers_actions():
    blocks = _build_blocks(_member(), [_item()], narrative=None)
    actions = [b for b in blocks if b["type"] == "actions"]
    assert actions, "a briefing item should be actionable in place"

    action_ids = {e["action_id"] for e in actions[0]["elements"]}
    assert {ACTION_ASK, ACTION_SNOOZE, ACTION_LESS} <= action_ids


def test_actions_carry_the_item_identity():
    """A button press must be traceable to the item it came from."""
    item = _item()
    blocks = _build_blocks(_member(), [item], narrative=None)
    element = [b for b in blocks if b["type"] == "actions"][0]["elements"][0]
    assert str(item.entity_id) in element["value"]


def test_empty_briefing_renders_no_action_rows():
    blocks = _build_blocks(_member(), [], narrative=None)
    assert not [b for b in blocks if b["type"] == "actions"]


# ── Handling ──────────────────────────────────────────────────────────


@pytest.fixture
def slack_calls():
    calls = {"posted": [], "ephemeral": []}

    async def _post(_token, channel, text, thread_ts=None, blocks=None):
        calls["posted"].append(text)
        return {"ok": True}

    async def _ephemeral(_token, channel, user, text, thread_ts=None):
        calls["ephemeral"].append(text)
        return {"ok": True}

    principal = Principal(
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        email="ada@example.com",
        surface=Surface.SLACK,
        audience=Audience.PRIVATE,
        member_id=uuid.uuid4(),
    )

    with patch("src.slack.actions.post_message", new=_post), patch(
        "src.slack.actions.post_ephemeral", new=_ephemeral
    ), patch("src.slack.actions.get_bot_token", new=AsyncMock(return_value="xoxb-test")), patch(
        "src.slack.actions.principal_for_slack_user", new=AsyncMock(return_value=principal)
    ):
        yield calls


def _payload(action_id, value="entity:abc"):
    return {
        "type": "block_actions",
        "user": {"id": "U1"},
        "channel": {"id": "D1"},
        "message": {"ts": "111.1"},
        "actions": [{"action_id": action_id, "value": value}],
    }


@pytest.mark.asyncio
async def test_ask_starts_a_thread_on_the_item(slack_calls):
    with patch("src.slack.actions.explain_item", new=AsyncMock(return_value="It blocks two engineers.")):
        await handle_block_action(AsyncMock(), uuid.uuid4(), _payload(ACTION_ASK))

    assert slack_calls["posted"], "the answer should be visible in the thread"
    assert "blocks two engineers" in slack_calls["posted"][0]


@pytest.mark.asyncio
async def test_snooze_confirms_privately(slack_calls):
    with patch("src.slack.actions.record_feedback", new=AsyncMock()) as record:
        await handle_block_action(AsyncMock(), uuid.uuid4(), _payload(ACTION_SNOOZE))

    assert slack_calls["ephemeral"], "confirmation belongs to the person who pressed it"
    assert not slack_calls["posted"]
    record.assert_awaited()


@pytest.mark.asyncio
async def test_less_like_this_is_recorded(slack_calls):
    """A feedback button that changes nothing teaches people not to press it."""
    with patch("src.slack.actions.record_feedback", new=AsyncMock()) as record:
        await handle_block_action(AsyncMock(), uuid.uuid4(), _payload(ACTION_LESS))

    record.assert_awaited()
    assert record.await_args.kwargs["signal"] == ACTION_LESS
    assert slack_calls["ephemeral"]


@pytest.mark.asyncio
async def test_unknown_action_is_ignored(slack_calls):
    await handle_block_action(AsyncMock(), uuid.uuid4(), _payload("something_else"))
    assert not slack_calls["posted"]
    assert not slack_calls["ephemeral"]
