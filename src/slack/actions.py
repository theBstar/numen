"""Make a briefing item something you can act on where you read it.

A notification whose only call to action is "open the dashboard" is a dead
end, and the well-documented failure of digest bots is that people stop
reading them. These three buttons turn each item into the opening turn of a
conversation instead.

"Less like this" writes real feedback. A button that changes nothing teaches
people that pressing buttons changes nothing.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.core import run_agent_to_text
from src.agent.principal import Principal
from src.slack.client import get_bot_token, post_ephemeral, post_message
from src.slack.identity import principal_for_slack_user

logger = logging.getLogger(__name__)

ACTION_ASK = "numen_ask"
ACTION_SNOOZE = "numen_snooze"
ACTION_LESS = "numen_less"

_VALUE_PREFIX = "entity:"

SNOOZED = "Snoozed. I will leave this out of tomorrow's briefing."
NOTED = "Noted - I will surface less like this."
NO_ACCOUNT = "I could not find a Numen account for you in this workspace."


def encode_value(entity_id) -> str:
    return f"{_VALUE_PREFIX}{entity_id}"


def decode_value(value: str) -> str | None:
    if value and value.startswith(_VALUE_PREFIX):
        return value[len(_VALUE_PREFIX) :]
    return None


def build_item_actions(entity_id, title: str) -> dict:
    """The action row shown under one briefing item."""
    value = encode_value(entity_id)
    return {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "action_id": ACTION_ASK,
                "text": {"type": "plain_text", "text": "Why this?"},
                "value": value,
            },
            {
                "type": "button",
                "action_id": ACTION_SNOOZE,
                "text": {"type": "plain_text", "text": "Snooze"},
                "value": value,
            },
            {
                "type": "button",
                "action_id": ACTION_LESS,
                "text": {"type": "plain_text", "text": "Less like this"},
                "value": value,
            },
        ],
    }


async def record_feedback(
    db: AsyncSession,
    org_id: UUID,
    *,
    member_id: UUID | None,
    entity_id: str | None,
    signal: str,
) -> None:
    """Persist a signal so ranking can learn from it.

    Stored on the urgency cache row for the item, which is what the next
    briefing reads. Failure here must never break the reply.
    """
    from sqlalchemy import select

    from src.shared.models import UrgencyScoreCache

    if not entity_id:
        return

    try:
        result = await db.execute(
            select(UrgencyScoreCache).where(
                UrgencyScoreCache.org_id == org_id,
                UrgencyScoreCache.entity_id == UUID(entity_id),
            )
        )
        row = result.scalars().first()
        if row is None:
            return

        components = dict(row.score_components or {})
        feedback = dict(components.get("feedback") or {})
        feedback[signal] = feedback.get(signal, 0) + 1
        if member_id:
            feedback["last_member_id"] = str(member_id)
        components["feedback"] = feedback
        row.score_components = components
        await db.commit()
    except Exception:
        logger.exception("Could not record %s feedback for entity %s", signal, entity_id)


async def explain_item(db: AsyncSession, principal: Principal, entity_id: str | None) -> str:
    """Ask the agent why an item was surfaced, grounded in the graph."""
    question = (
        "Explain why this work needs attention now, citing the signals and the goal "
        "it connects to. Be brief."
    )
    if entity_id:
        question = f"{question} The item has id {entity_id}."
    return await run_agent_to_text(db, principal, question)


async def handle_block_action(db: AsyncSession, org_id: UUID, payload: dict) -> None:
    """Respond to a button on a briefing item. Never raises."""
    actions = payload.get("actions") or []
    if not actions:
        return

    action_id = actions[0].get("action_id", "")
    if action_id not in (ACTION_ASK, ACTION_SNOOZE, ACTION_LESS):
        return

    entity_id = decode_value(actions[0].get("value", ""))
    slack_user = (payload.get("user") or {}).get("id", "")
    channel = (payload.get("channel") or {}).get("id", "")
    thread_ts = (payload.get("message") or {}).get("ts")

    token = await get_bot_token(db, org_id)
    if not token:
        return

    # A briefing arrives as a direct message, so this is a private audience.
    principal = await principal_for_slack_user(db, org_id, slack_user_id=slack_user, is_direct_message=True)
    if principal is None:
        await post_ephemeral(token, channel, slack_user, NO_ACCOUNT, thread_ts=thread_ts)
        return

    try:
        if action_id == ACTION_ASK:
            answer = await explain_item(db, principal, entity_id)
            await post_message(token, channel, answer, thread_ts=thread_ts)
            return

        await record_feedback(
            db,
            org_id,
            member_id=principal.member_id,
            entity_id=entity_id,
            signal=action_id,
        )
        await post_ephemeral(
            token,
            channel,
            slack_user,
            SNOOZED if action_id == ACTION_SNOOZE else NOTED,
            thread_ts=thread_ts,
        )
    except Exception:
        logger.exception("Slack action %s failed for org %s", action_id, org_id)
