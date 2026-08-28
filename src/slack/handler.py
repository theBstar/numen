"""Route Slack events into the agent, and render what comes back.

This is an adapter in the strict sense: it resolves identity and threading,
consumes the core's events, and renders them for Slack. It never builds a
prompt and never calls a tool - that all lives in ``src.agent.core``, which
is what stops Slack becoming a second, divergent agent.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.core import run_agent
from src.agent.events import ErrorEvent, SanitizedEvent, TokenEvent
from src.agent.principal import Principal
from src.chat.service import converse, get_or_create_external_conversation
from src.slack.client import get_bot_token, post_ephemeral, post_message, set_status
from src.slack.identity import principal_for_slack_user

logger = logging.getLogger(__name__)

_MENTION = re.compile(r"<@[A-Z0-9]+>")

# Slack subtypes that are edits, joins and other housekeeping rather than
# somebody talking to us.
_IGNORED_SUBTYPES = {
    "bot_message",
    "message_changed",
    "message_deleted",
    "channel_join",
    "channel_leave",
    "thread_broadcast",
}

NO_ACCOUNT = (
    "I could not find a Numen account for you in this workspace. "
    "Ask an admin to invite you, then mention me again."
)
FAILED = "I could not finish that. Please try again in a moment."


def should_handle(event: dict) -> bool:
    """Whether this event is somebody addressing Numen.

    Bot messages are excluded first: answering our own posts would loop.
    """
    if event.get("bot_id") or event.get("subtype") in _IGNORED_SUBTYPES:
        return False

    if not event.get("user") or not (event.get("text") or "").strip():
        return False

    kind = event.get("type")
    if kind == "app_mention":
        return True
    if kind == "message":
        # In a channel we only answer when mentioned, which arrives as
        # app_mention instead. Direct messages are always for us.
        return event.get("channel_type") in ("im", "mpim")
    return False


def _clean_text(raw: str) -> str:
    return _MENTION.sub("", raw or "").strip()


def _thread_key(event: dict) -> str:
    """Slack threads are identified by their parent message timestamp."""
    return event.get("thread_ts") or event.get("ts") or ""


async def answer_in_thread(
    db: AsyncSession,
    principal: Principal,
    conversation_id: UUID,
    text: str,
    *,
    member=None,
) -> str:
    """Run the agent for a Slack turn and return the finished reply.

    Slack shows one settled message rather than a token stream, so the
    events are collected here instead of being rendered as they arrive.
    """
    parts: list[str] = []
    replacement: str | None = None
    failed = False

    if member is not None:
        stream = converse(
            db,
            principal.org_id,
            member,
            conversation_id,
            text,
            surface=principal.surface,
            audience=principal.audience,
        )
    else:
        stream = run_agent(db, principal, text)

    async for event in stream:
        if isinstance(event, TokenEvent):
            parts.append(event.content)
        elif isinstance(event, SanitizedEvent):
            replacement = event.content
        elif isinstance(event, ErrorEvent):
            failed = True

    reply = replacement if replacement is not None else "".join(parts)
    if failed and not reply.strip():
        return FAILED
    return reply.strip() or FAILED


async def handle_slack_event(db: AsyncSession, org_id: UUID, event: dict) -> None:
    """Answer one Slack message. Never raises: Slack only needs the ack."""
    if not should_handle(event):
        return

    channel = event.get("channel", "")
    slack_user = event.get("user", "")
    thread_ts = _thread_key(event)
    is_dm = event.get("channel_type") in ("im", "mpim")
    question = _clean_text(event.get("text", ""))

    token = await get_bot_token(db, org_id)
    if not token:
        logger.warning("Slack event for org %s but no bot token stored", org_id)
        return

    principal = await principal_for_slack_user(
        db, org_id, slack_user_id=slack_user, is_direct_message=is_dm
    )
    if principal is None:
        # Private, so an unrecognised person is not announced to the channel.
        await post_ephemeral(token, channel, slack_user, NO_ACCOUNT, thread_ts=thread_ts)
        return

    try:
        await set_status(token, channel, thread_ts, "is thinking...")
    except Exception:
        logger.debug("Could not set Slack status", exc_info=True)

    try:
        conversation = await get_or_create_external_conversation(
            db,
            org_id,
            principal.member_id,
            external_ref=f"slack:{channel}:{thread_ts}",
            title=question,
        )
        reply = await answer_in_thread(db, principal, conversation.id, question)
    except Exception:
        logger.exception("Slack agent turn failed for org %s", org_id)
        reply = FAILED

    await post_message(token, channel, reply, thread_ts=thread_ts)
