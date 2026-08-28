"""Tests for the surface-agnostic agent event stream."""

import json

from src.agent.events import (
    CitationEvent,
    DoneEvent,
    ElicitationEvent,
    ErrorEvent,
    EventType,
    SanitizedEvent,
    StatusEvent,
    TokenEvent,
    ToolEndEvent,
    ToolStartEvent,
    to_sse,
)


def test_token_event_serializes():
    event = TokenEvent(content="hello")
    assert event.type is EventType.TOKEN
    assert event.to_dict() == {"type": "token", "content": "hello"}


def test_status_event_carries_human_readable_label():
    """Slack renders this as a session status line; web as a trace."""
    event = StatusEvent(content="Checking Linear")
    assert event.to_dict() == {"type": "status", "content": "Checking Linear"}


def test_tool_events_carry_tool_name():
    assert ToolStartEvent(tool="list_tasks").to_dict() == {"type": "tool_start", "tool": "list_tasks"}
    assert ToolEndEvent(tool="list_tasks").to_dict() == {"type": "tool_end", "tool": "list_tasks"}


def test_citation_event_carries_entities():
    entities = [{"id": "1", "name": "Checkout", "type": "feature"}]
    payload = CitationEvent(entities=entities).to_dict()
    assert payload["type"] == "citation"
    assert payload["entities"] == entities


def test_elicitation_event_is_distinct_from_error():
    """An agent asking a question is not a failure."""
    assert ElicitationEvent(content="Which project?").type is EventType.ELICITATION
    assert ErrorEvent(content="boom").type is EventType.ERROR
    assert ElicitationEvent(content="x").type is not ErrorEvent(content="x").type


def test_sanitized_and_done_events():
    assert SanitizedEvent(content="clean").to_dict() == {"type": "sanitized", "content": "clean"}
    assert DoneEvent().to_dict() == {"type": "done"}


def test_to_sse_frames_an_event():
    """SSE framing belongs at the web edge, never in the core."""
    frame = to_sse(TokenEvent(content="hi"))
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n")
    assert json.loads(frame[6:].strip()) == {"type": "token", "content": "hi"}


def test_to_sse_escapes_newlines_in_content():
    """A raw newline in the payload would terminate the SSE frame early."""
    frame = to_sse(TokenEvent(content="line one\nline two"))
    assert frame.count("\n\n") == 1
    assert json.loads(frame[6:].strip())["content"] == "line one\nline two"
