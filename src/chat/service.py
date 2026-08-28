"""Conversation storage and the web surface's use of the agent core.

The run loop itself lives in ``src.agent.core``; this module persists the
thread around it. Nothing here formats for a transport - the router does
that - so the same conversation records serve web, Slack and the API.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.core import extract_entities as _extract_entities  # noqa: F401  (kept for callers)
from src.agent.core import run_agent
from src.agent.events import (
    AgentEvent,
    CitationEvent,
    SanitizedEvent,
    TokenEvent,
    ToolStartEvent,
)
from src.agent.principal import Audience, Principal, Surface
from src.chat.safety import redact_tool_calls
from src.shared.models import ChatMessage, Conversation, OrgMember
from src.shared.types import ChatRole

logger = logging.getLogger(__name__)


def principal_for_member(
    org_id: UUID,
    member: OrgMember,
    *,
    surface: Surface = Surface.WEB,
    audience: Audience = Audience.PRIVATE,
) -> Principal:
    """Build the agent's view of a signed-in org member."""
    return Principal(
        org_id=org_id,
        user_id=member.user_id or member.id,
        email=member.email,
        surface=surface,
        audience=audience,
        name=member.display_name,
        member_id=member.id,
    )


async def create_conversation(
    db: AsyncSession, org_id: UUID, member_id: UUID, title: str | None = None
) -> Conversation:
    conv = Conversation(org_id=org_id, member_id=member_id, title=title)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def get_or_create_external_conversation(
    db: AsyncSession,
    org_id: UUID,
    member_id: UUID,
    external_ref: str,
    title: str | None = None,
) -> Conversation:
    """Find the conversation behind a surface's own thread id, or start one.

    Lets a Slack thread, a CLI session and a web conversation all be the
    same primitive, so history and provenance work identically everywhere.
    """
    result = await db.execute(
        select(Conversation).where(
            and_(Conversation.org_id == org_id, Conversation.external_ref == external_ref)
        )
    )
    existing = result.scalars().first()
    if existing is not None:
        return existing

    conversation = Conversation(
        org_id=org_id,
        member_id=member_id,
        external_ref=external_ref,
        title=title[:100] if title else None,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def get_conversations(db: AsyncSession, org_id: UUID, member_id: UUID) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(and_(Conversation.org_id == org_id, Conversation.member_id == member_id))
        .order_by(Conversation.updated_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_messages(
    db: AsyncSession,
    conversation_id: UUID,
    org_id: UUID,
) -> list[ChatMessage]:
    # Verify conversation belongs to the org
    conv_stmt = select(Conversation).where(and_(Conversation.id == conversation_id, Conversation.org_id == org_id))
    conv_result = await db.execute(conv_stmt)
    if conv_result.scalars().first() is None:
        return []

    stmt = (
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id).order_by(ChatMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_conversation(db: AsyncSession, conversation_id: UUID, org_id: UUID) -> None:
    # Verify conversation belongs to the org before deleting
    stmt = select(Conversation).where(and_(Conversation.id == conversation_id, Conversation.org_id == org_id))
    result = await db.execute(stmt)
    conv = result.scalars().first()
    if not conv:
        return

    msgs = await get_messages(db, conversation_id, org_id)
    for msg in msgs:
        await db.delete(msg)
    await db.delete(conv)
    await db.commit()


def _history_pairs(messages: list[ChatMessage]) -> list[tuple[str, str]]:
    """Turn stored messages into the (role, text) pairs the core expects."""
    pairs: list[tuple[str, str]] = []
    for msg in messages:
        if msg.role == ChatRole.USER:
            pairs.append(("user", msg.content))
        elif msg.role == ChatRole.ASSISTANT:
            pairs.append(("assistant", msg.content))
    return pairs


async def converse(
    db: AsyncSession,
    org_id: UUID,
    member: OrgMember,
    conversation_id: UUID,
    user_input: str,
    *,
    surface: Surface = Surface.WEB,
    audience: Audience = Audience.PRIVATE,
) -> AsyncIterator[AgentEvent]:
    """Persist a turn and stream the agent's typed events back.

    Yields the same events on every surface; callers decide how to render
    them. The assistant reply is stored once the run finishes.
    """
    user_msg = ChatMessage(org_id=org_id, conversation_id=conversation_id, role=ChatRole.USER, content=user_input)
    db.add(user_msg)
    await db.commit()

    stored = await get_messages(db, conversation_id, org_id)
    history = _history_pairs(stored[:-1])

    principal = principal_for_member(org_id, member, surface=surface, audience=audience)

    reply = ""
    replacement: str | None = None
    tool_calls: list[dict] = []
    entities: list[dict] | None = None

    async for event in run_agent(db, principal, user_input, history=history):
        if isinstance(event, TokenEvent):
            reply += event.content
        elif isinstance(event, ToolStartEvent):
            tool_calls.append({"tool": event.tool})
        elif isinstance(event, CitationEvent):
            entities = event.entities
        elif isinstance(event, SanitizedEvent):
            replacement = event.content
        yield event

    final = replacement if replacement is not None else reply
    if final:
        await _store_reply(db, org_id, conversation_id, user_input, final, tool_calls, entities)


async def _store_reply(
    db: AsyncSession,
    org_id: UUID,
    conversation_id: UUID,
    user_input: str,
    reply: str,
    tool_calls: list[dict],
    entities: list[dict] | None,
) -> None:
    db.add(
        ChatMessage(
            org_id=org_id,
            conversation_id=conversation_id,
            role=ChatRole.ASSISTANT,
            content=reply,
            tool_calls=redact_tool_calls(tool_calls) if tool_calls else None,
            referenced_entities=entities,
        )
    )

    result = await db.execute(
        select(Conversation).where(and_(Conversation.id == conversation_id, Conversation.org_id == org_id))
    )
    conversation = result.scalars().first()
    if conversation is not None and not conversation.title:
        conversation.title = user_input[:100]

    await db.commit()
