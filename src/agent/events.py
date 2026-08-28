"""The event vocabulary every Numen surface renders.

The agent core emits these; adapters translate them. Web frames them as SSE,
Slack maps them onto session status and streamed chunks, a CLI prints them.
Nothing in this module knows about HTTP, Slack, or any other transport - that
is what lets one agent serve every surface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum


class EventType(str, Enum):
    """Kinds of thing an agent run can emit."""

    STATUS = "status"
    """Human-readable progress, e.g. "Checking Linear"."""

    TOKEN = "token"
    """A chunk of the reply text."""

    TOOL_START = "tool_start"
    TOOL_END = "tool_end"

    CITATION = "citation"
    """Entities the answer drew on, for provenance."""

    ELICITATION = "elicitation"
    """The agent asking the user a question. Not a failure."""

    SANITIZED = "sanitized"
    """Replaces text already emitted, when redaction changed it."""

    ERROR = "error"
    DONE = "done"


@dataclass(frozen=True)
class AgentEvent:
    """Base class for everything the core emits."""

    type: EventType = field(init=False)

    def to_dict(self) -> dict:
        raise NotImplementedError


@dataclass(frozen=True)
class TokenEvent(AgentEvent):
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.TOKEN)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "content": self.content}


@dataclass(frozen=True)
class StatusEvent(AgentEvent):
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.STATUS)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "content": self.content}


@dataclass(frozen=True)
class ToolStartEvent(AgentEvent):
    tool: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.TOOL_START)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "tool": self.tool}


@dataclass(frozen=True)
class ToolEndEvent(AgentEvent):
    tool: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.TOOL_END)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "tool": self.tool}


@dataclass(frozen=True)
class CitationEvent(AgentEvent):
    entities: list[dict]

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.CITATION)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "entities": self.entities}


@dataclass(frozen=True)
class ElicitationEvent(AgentEvent):
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.ELICITATION)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "content": self.content}


@dataclass(frozen=True)
class SanitizedEvent(AgentEvent):
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.SANITIZED)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "content": self.content}


@dataclass(frozen=True)
class ErrorEvent(AgentEvent):
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.ERROR)

    def to_dict(self) -> dict:
        return {"type": self.type.value, "content": self.content}


@dataclass(frozen=True)
class DoneEvent(AgentEvent):
    def __post_init__(self) -> None:
        object.__setattr__(self, "type", EventType.DONE)

    def to_dict(self) -> dict:
        return {"type": self.type.value}


def to_sse(event: AgentEvent) -> str:
    """Frame an event for an HTTP event stream.

    json.dumps escapes newlines, which would otherwise terminate the frame.
    """
    return f"data: {json.dumps(event.to_dict())}\n\n"
