"""Tests for the surface-agnostic agent run loop."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.core import run_agent
from src.agent.events import EventType
from src.agent.principal import Audience, Principal, Surface


def _principal(**overrides):
    base = {
        "org_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "email": "asker@example.com",
        "surface": Surface.WEB,
    }
    base.update(overrides)
    return Principal(**base)


class _Chunk:
    def __init__(self, content):
        self.content = content


def _agent_yielding(*events):
    async def _stream(*_args, **_kwargs):
        for event in events:
            yield event

    agent = MagicMock()
    agent.astream_events = _stream
    return agent


def _token(text):
    return {"event": "on_chat_model_stream", "data": {"chunk": _Chunk(text)}}


async def _collect(principal=None, agent=None, user_input="hello", history=None):
    principal = principal or _principal()
    agent = agent or _agent_yielding(_token("hi"))
    with patch("src.agent.core.build_chat_agent", return_value=agent):
        return [event async for event in run_agent(AsyncMock(), principal, user_input, history=history)]


@pytest.mark.asyncio
async def test_yields_typed_events_not_wire_strings():
    """The core must stay free of any transport's framing."""
    events = await _collect()
    assert all(not isinstance(e, str) for e in events)
    assert all(hasattr(e, "to_dict") for e in events)


@pytest.mark.asyncio
async def test_streams_tokens_and_finishes_with_done():
    events = await _collect(agent=_agent_yielding(_token("Hello "), _token("world")))
    kinds = [e.type for e in events]
    assert kinds.count(EventType.TOKEN) == 2
    assert kinds[-1] is EventType.DONE


@pytest.mark.asyncio
async def test_maps_tool_events_and_emits_status():
    """Slack renders status; every surface gets the tool boundaries."""
    agent = _agent_yielding(
        {"event": "on_tool_start", "name": "list_tasks"},
        {"event": "on_tool_end", "name": "list_tasks", "data": {"output": "[]"}},
    )
    kinds = [e.type for e in await _collect(agent=agent)]
    assert EventType.TOOL_START in kinds
    assert EventType.TOOL_END in kinds
    assert EventType.STATUS in kinds


@pytest.mark.asyncio
async def test_emits_citations_from_tool_output():
    output = '{"person": {"id": "abc", "name": "Ada", "type": "person"}}'
    agent = _agent_yielding(
        {"event": "on_tool_end", "name": "get_person_workload", "data": {"output": output}},
        _token("Ada has two tasks."),
    )
    events = await _collect(agent=agent)
    citations = [e for e in events if e.type is EventType.CITATION]
    assert citations
    assert citations[0].entities[0]["name"] == "Ada"


@pytest.mark.asyncio
async def test_redaction_emits_a_replacement():
    leaked = "the key is sk-abcdefghijklmnopqrstuvwxyz0123"
    events = await _collect(agent=_agent_yielding(_token(leaked)))
    sanitized = [e for e in events if e.type is EventType.SANITIZED]
    assert sanitized
    assert "sk-abcdefghijklmnopqrstuvwxyz0123" not in sanitized[0].content


@pytest.mark.asyncio
async def test_clean_output_emits_no_replacement():
    events = await _collect(agent=_agent_yielding(_token("Three tasks close Friday.")))
    assert not [e for e in events if e.type is EventType.SANITIZED]


@pytest.mark.asyncio
async def test_agent_failure_becomes_an_error_event_then_done():
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("model unreachable")
        yield  # pragma: no cover

    agent = MagicMock()
    agent.astream_events = _boom

    events = await _collect(agent=agent)
    kinds = [e.type for e in events]
    assert EventType.ERROR in kinds
    assert kinds[-1] is EventType.DONE


@pytest.mark.asyncio
async def test_error_event_does_not_leak_internals():
    async def _boom(*_args, **_kwargs):
        raise RuntimeError("postgresql://user:password@db/numen refused")
        yield  # pragma: no cover

    agent = MagicMock()
    agent.astream_events = _boom

    errors = [e for e in await _collect(agent=agent) if e.type is EventType.ERROR]
    assert errors
    assert "password" not in errors[0].content


@pytest.mark.asyncio
async def test_shared_audience_gets_read_only_tooling():
    """A public channel principal must not be handed write tools."""
    captured = {}

    def _capture(ctx, **_kwargs):
        captured["names"] = {t.name for t in __import__(
            "src.agent.registry", fromlist=["build_langchain_tools"]
        ).build_langchain_tools(ctx)}
        return _agent_yielding(_token("ok"))

    principal = _principal(surface=Surface.SLACK, audience=Audience.SHARED)
    with patch("src.agent.core.build_chat_agent", side_effect=_capture):
        [e async for e in run_agent(AsyncMock(), principal, "hi")]

    assert "create_task" not in captured["names"]
    assert "get_context" not in captured["names"]


@pytest.mark.asyncio
async def test_history_is_passed_to_the_model():
    captured = {}

    async def _stream(payload, **_kwargs):
        captured["messages"] = payload["messages"]
        for event in (_token("ok"),):
            yield event

    agent = MagicMock()
    agent.astream_events = _stream

    history = [("user", "first question"), ("assistant", "first answer")]
    with patch("src.agent.core.build_chat_agent", return_value=agent):
        [e async for e in run_agent(AsyncMock(), _principal(), "second question", history=history)]

    contents = [m.content for m in captured["messages"]]
    assert contents == ["first question", "first answer", "second question"]


@pytest.mark.asyncio
async def test_result_collects_the_final_text():
    """Adapters that cannot stream need the whole reply in one piece."""
    from src.agent.core import run_agent_to_text

    agent = _agent_yielding(_token("Three "), _token("tasks."))
    with patch("src.agent.core.build_chat_agent", return_value=agent):
        text = await run_agent_to_text(AsyncMock(), _principal(), "hi")
    assert text == "Three tasks."
