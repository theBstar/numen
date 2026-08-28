"""The agent run loop, shared by every surface.

This module knows nothing about HTTP, Slack, or the command line. It takes a
caller and a question, and yields typed events. Adapters render those events
however their transport wants: the web frames them as SSE, Slack maps them
onto session status and streamed chunks, a CLI prints them.

Keeping model and tool calls in here - and only here - is what stops the
agent forking into a different implementation per surface.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.prebuilt import create_react_agent
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.events import (
    AgentEvent,
    CitationEvent,
    DoneEvent,
    ErrorEvent,
    SanitizedEvent,
    StatusEvent,
    TokenEvent,
    ToolEndEvent,
    ToolStartEvent,
)
from src.agent.principal import Principal
from src.agent.prompts import system_prompt
from src.agent.registry import ToolContext, build_langchain_tools
from src.chat.safety import sanitize_response
from src.config import settings
from src.llm.provider import build_client_kwargs, resolve_chat_model

logger = logging.getLogger(__name__)

GENERIC_ERROR = "Something went wrong while working on that. Please try again."

# Turned into "Checking Linear..." style status lines for surfaces that show
# progress. Anything absent falls back to the tool name.
_TOOL_LABELS = {
    "search_entities": "Searching the graph",
    "list_entities_by_type": "Listing records",
    "list_tasks": "Looking up tasks",
    "get_task_context": "Reading task context",
    "list_goals": "Reading goals",
    "get_goal_progress": "Checking goal progress",
    "get_goal_coverage": "Checking goal coverage",
    "get_urgency_scores": "Ranking by urgency",
    "get_person_workload": "Checking workload",
    "get_person_tasks": "Looking up assigned tasks",
    "get_person_prs": "Looking up pull requests",
    "get_project_stats": "Reading project stats",
    "get_blocking_chain": "Tracing blockers",
    "get_delayed_projects": "Finding delayed projects",
    "get_team_summary": "Summarising the team",
    "get_briefing": "Reading the briefing",
    "get_context": "Searching documents",
    "find_matching_task": "Checking for duplicates",
    "create_task": "Creating the task",
    "update_task_status": "Updating status",
    "propose_prd_update": "Drafting a proposal",
}


def build_chat_agent(ctx: ToolContext, *, streaming: bool = True):
    """Create a LangGraph agent bound to this caller's tools and prompt."""
    from langchain_openai import ChatOpenAI

    client_kwargs = build_client_kwargs(settings)
    llm = ChatOpenAI(
        model=resolve_chat_model(settings),
        api_key=client_kwargs["api_key"],
        base_url=client_kwargs.get("base_url"),
        streaming=streaming,
    )
    tools = build_langchain_tools(ctx)
    return create_react_agent(llm, tools, prompt=SystemMessage(content=system_prompt(ctx.principal)))


def extract_entities(raw: str) -> list[dict]:
    """Pull entity references out of tool output for provenance.

    Walks the parsed JSON for dicts carrying id, name and type.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    found: list[dict] = []

    def _walk(node: object) -> None:
        if isinstance(node, dict):
            if "id" in node and "name" in node and "type" in node:
                found.append(
                    {
                        "id": str(node["id"]),
                        "name": str(node["name"]),
                        "type": str(node["type"]),
                    }
                )
            for value in node.values():
                _walk(value)
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(data)
    return found


def _to_messages(history: Sequence[tuple[str, str]] | None, user_input: str) -> list:
    messages = []
    for role, content in history or []:
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=user_input))
    return messages


async def run_agent(
    db: AsyncSession,
    principal: Principal,
    user_input: str,
    *,
    history: Sequence[tuple[str, str]] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Answer a question, yielding typed events as the work happens.

    Never raises: model and tool failures surface as an ``ErrorEvent`` so
    that every adapter can render a failure the same way. The stream always
    ends with ``DoneEvent``.
    """
    ctx = ToolContext(db=db, principal=principal)
    reply = ""
    citations: dict[str, dict] = {}

    try:
        agent = build_chat_agent(ctx)

        async for event in agent.astream_events({"messages": _to_messages(history, user_input)}, version="v2"):
            kind = event.get("event", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                content = getattr(chunk, "content", None)
                if isinstance(content, str) and content:
                    reply += content
                    yield TokenEvent(content=content)

            elif kind == "on_tool_start":
                name = event.get("name", "")
                yield StatusEvent(content=_TOOL_LABELS.get(name, name.replace("_", " ").capitalize()))
                yield ToolStartEvent(tool=name)

            elif kind == "on_tool_end":
                name = event.get("name", "")
                output = event.get("data", {}).get("output", "")
                for entity in extract_entities(str(output)):
                    citations[entity["id"]] = entity
                yield ToolEndEvent(tool=name)

    except Exception:
        # The underlying message can carry connection strings or keys, so it
        # goes to the log and never to the caller.
        logger.exception("Agent run failed for org %s", principal.org_id)
        yield ErrorEvent(content=GENERIC_ERROR)
        yield DoneEvent()
        return

    if citations:
        yield CitationEvent(entities=list(citations.values()))

    # Tokens were emitted raw: the safety patterns span chunk boundaries and
    # cannot be applied per token. If redaction changed anything, send the
    # clean text so adapters can replace what they already rendered.
    clean = sanitize_response(reply)
    if clean != reply:
        yield SanitizedEvent(content=clean)

    yield DoneEvent()


async def run_agent_to_text(
    db: AsyncSession,
    principal: Principal,
    user_input: str,
    *,
    history: Sequence[tuple[str, str]] | None = None,
) -> str:
    """Run the agent and return only the finished reply.

    For callers that cannot stream: slash commands, the one-shot HTTP
    endpoint, and any client asking for a non-streaming response.
    """
    parts: list[str] = []
    replacement: str | None = None
    error: str | None = None

    async for event in run_agent(db, principal, user_input, history=history):
        if isinstance(event, TokenEvent):
            parts.append(event.content)
        elif isinstance(event, SanitizedEvent):
            replacement = event.content
        elif isinstance(event, ErrorEvent):
            error = event.content

    if error and not parts:
        return error
    return replacement if replacement is not None else "".join(parts)
