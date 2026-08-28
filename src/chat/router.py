"""FastAPI routes for AI chat."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.events import to_sse
from src.api.dependencies import get_current_member
from src.api.rate_limit import limiter
from src.api.schemas import (
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSendRequest,
    ConversationListResponse,
    ConversationResponse,
    ErrorResponse,
)
from src.chat.safety import redact_tool_calls
from src.chat.service import (
    converse,
    create_conversation,
    delete_conversation,
    get_conversations,
    get_messages,
)
from src.shared.database import get_db
from src.shared.models import OrgMember

router = APIRouter(prefix="/api/orgs/{org_id}/chat", tags=["chat"])


@router.post(
    "/conversations",
    response_model=ConversationResponse,
    summary="Create conversation",
    responses={404: {"model": ErrorResponse}},
)
async def create_conversation_endpoint(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Create a new chat conversation for the current member."""
    conv = await create_conversation(db, org_id, member.id)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
    summary="List conversations",
    responses={404: {"model": ErrorResponse}},
)
async def list_conversations_endpoint(
    org_id: UUID,
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """List all chat conversations for the current member."""
    convs = await get_conversations(db, org_id, member.id)
    return ConversationListResponse(
        items=[
            ConversationResponse(id=c.id, title=c.title, created_at=c.created_at, updated_at=c.updated_at)
            for c in convs
        ]
    )


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageListResponse,
    summary="List messages",
    responses={404: {"model": ErrorResponse}},
)
async def list_messages_endpoint(
    org_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List all messages in a conversation."""
    msgs = await get_messages(db, conversation_id, org_id)
    return ChatMessageListResponse(
        items=[
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                tool_calls=redact_tool_calls(m.tool_calls),
                referenced_entities=m.referenced_entities,
                created_at=m.created_at,
            )
            for m in msgs
        ]
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_class=StreamingResponse,
    summary="Send message",
    responses={404: {"model": ErrorResponse}},
)
@limiter.limit("30/minute")
async def send_message_endpoint(
    request: Request,
    org_id: UUID,
    conversation_id: UUID,
    body: ChatSendRequest,
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Send a message and receive a streaming AI response (SSE).

    This is the most expensive endpoint in the app - each call can fan out
    into several model and tool round trips - so it is rate limited per user.
    """

    async def _frames() -> AsyncIterator[str]:
        async for event in converse(db, org_id, member, conversation_id, body.content):
            yield to_sse(event)

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=204,
    summary="Delete conversation",
    responses={404: {"model": ErrorResponse}},
)
async def delete_conversation_endpoint(
    org_id: UUID,
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Delete a chat conversation and all its messages."""
    await delete_conversation(db, conversation_id, org_id)
