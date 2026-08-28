"""HTTP surfaces for the agent: one-shot ask, and OpenAI compatibility.

Two endpoints over the same core. ``/api/ask`` speaks Numen's own typed
events, so it loses nothing. ``/api/v1/chat/completions`` speaks the shape
every SDK and chat client already understands, which is what makes Numen
callable from anywhere without a bespoke client.

The OpenAI shape is deliberately lossy. Its protocol assumes the *caller*
executes tools; Numen executes its own, so the loop is collapsed and the
response carries the finished text with ``finish_reason: "stop"``. Tool
activity surfaces as progress, never as tool calls a client must run.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.core import run_agent, run_agent_to_text
from src.agent.events import SanitizedEvent, StatusEvent, TokenEvent, to_sse
from src.agent.principal import Audience, Principal, Surface
from src.api.rate_limit import limiter
from src.mcp.auth import validate_api_key
from src.shared.database import get_db

router = APIRouter(tags=["agent"])

_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# ── Auth ──────────────────────────────────────────────────────────────


async def principal_from_api_key(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(None, alias="Authorization"),
) -> Principal:
    """Resolve the caller from a Numen API key.

    The org always comes from the credential, never from the request body,
    so a caller cannot address an organisation their key does not belong to.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send 'Authorization: Bearer <numen key>'.",
        )

    resolved = await validate_api_key(db, authorization.split(" ", 1)[1].strip())
    if resolved is None:
        raise HTTPException(status_code=401, detail="Invalid or expired API key.")

    org_id, user_id = resolved
    return Principal(
        org_id=org_id,
        user_id=user_id,
        email="api-key@numen.local",
        surface=Surface.API,
        audience=Audience.PRIVATE,
    )


# ── Schemas ───────────────────────────────────────────────────────────


class AskRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000, description="What to ask")
    stream: bool = Field(default=False, description="Stream typed events instead of one reply")

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class AskResponse(BaseModel):
    answer: str


class ChatMessageIn(BaseModel):
    role: str
    content: str = ""


class ChatCompletionRequest(BaseModel):
    model: str = "numen"
    messages: list[ChatMessageIn]
    stream: bool = False


# ── One-shot, native shape ────────────────────────────────────────────


@router.post("/api/ask", response_model=None, summary="Ask Numen a question")
@limiter.limit("30/minute")
async def ask(
    request: Request,
    body: AskRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(principal_from_api_key),
):
    """Answer one question. Set ``stream`` for Numen's typed event stream."""
    if body.stream:

        async def _frames() -> AsyncIterator[str]:
            async for event in run_agent(db, principal, body.message):
                yield to_sse(event)

        return StreamingResponse(_frames(), media_type="text/event-stream", headers=_SSE_HEADERS)

    answer = await run_agent_to_text(db, principal, body.message)
    return AskResponse(answer=answer)


# ── OpenAI-compatible ─────────────────────────────────────────────────


def _split_messages(messages: list[ChatMessageIn]) -> tuple[str, list[tuple[str, str]]]:
    """Take the last user message as the question, the rest as history."""
    history: list[tuple[str, str]] = []
    question: str | None = None

    for index in range(len(messages) - 1, -1, -1):
        if messages[index].role == "user":
            question = messages[index].content
            history = [(m.role, m.content) for m in messages[:index] if m.role in ("user", "assistant")]
            break

    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="messages must contain a user message with content.")

    return question, history


def _completion_id() -> str:
    return f"chatcmpl-{uuid.uuid4().hex[:24]}"


@router.post("/api/v1/chat/completions", response_model=None, summary="OpenAI-compatible chat completions")
@limiter.limit("30/minute")
async def chat_completions(
    request: Request,
    body: ChatCompletionRequest,
    db: AsyncSession = Depends(get_db),
    principal: Principal = Depends(principal_from_api_key),
):
    """Answer in the shape every OpenAI-compatible client understands.

    Point any such client at this path as its base URL and Numen's agent
    stands in for a model, tools and all.
    """
    question, history = _split_messages(body.messages)
    completion_id = _completion_id()
    created = int(time.time())

    if body.stream:
        return StreamingResponse(
            _stream_openai(db, principal, question, history, completion_id, created, body.model),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
        )

    answer = await run_agent_to_text(db, principal, question, history=history)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": body.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        # Numen bills against the operator's own LLM credentials, so token
        # counts are reported as zero rather than invented.
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


async def _stream_openai(
    db: AsyncSession,
    principal: Principal,
    question: str,
    history: list[tuple[str, str]],
    completion_id: str,
    created: int,
    model: str,
) -> AsyncIterator[str]:
    """Map typed events onto OpenAI streaming chunks.

    Progress is sent as ``reasoning_content``, a field well-behaved clients
    ignore, so surfaces that understand it can show what the agent is doing
    without corrupting the reply for those that do not.
    """

    def _chunk(delta: dict, finish: str | None = None) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload)}\n\n"

    yield _chunk({"role": "assistant"})

    async for event in run_agent(db, principal, question, history=history):
        if isinstance(event, TokenEvent):
            yield _chunk({"content": event.content})
        elif isinstance(event, StatusEvent):
            yield _chunk({"reasoning_content": f"{event.content}\n"})
        elif isinstance(event, SanitizedEvent):
            # The reply had to be redacted after streaming; tell clients that
            # track it, and let the rest keep what they already rendered.
            yield _chunk({"reasoning_content": "[response redacted for safety]\n"})

    yield _chunk({}, finish="stop")
    yield "data: [DONE]\n\n"
