"""Who is asking, and what they are allowed to see.

Adapters resolve identity from whatever their transport offers - a JWT on the
web, an API key for the CLI and SDK, a Slack user mapping - and hand the core
this value object. The core never learns which surface it is serving.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from uuid import UUID


class Surface(str, Enum):
    """Where the conversation is happening. Informational for the core;
    load-bearing for prompt tone and rendering."""

    WEB = "web"
    SLACK = "slack"
    CLI = "cli"
    API = "api"
    MCP = "mcp"


class Audience(str, Enum):
    """Who can read the answer once it is delivered."""

    PRIVATE = "private"
    """One person: a web session, a DM, an ephemeral reply."""

    SHARED = "shared"
    """A channel other people can read."""


@dataclass(frozen=True)
class Principal:
    """The caller, plus what the surface permits.

    Two rules ride on ``audience``, both closing the same leak: an answer
    posted where others can read it must not quote records they may not be
    allowed to see, and must not mutate anything on the asker's behalf.
    """

    org_id: UUID
    user_id: UUID | None
    email: str
    surface: Surface
    audience: Audience = Audience.PRIVATE
    name: str | None = None
    member_id: UUID | None = None

    @property
    def can_write(self) -> bool:
        """Writes need a bound user and a private audience."""
        return self.user_id is not None and self.audience is Audience.PRIVATE

    @property
    def can_access_private_data(self) -> bool:
        """Whether the agent may ground on records beyond public ones."""
        return self.audience is Audience.PRIVATE

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]
