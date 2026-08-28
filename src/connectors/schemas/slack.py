"""Pydantic schemas for Slack entity properties.

These models validate properties stored on entities ingested from the Slack
REST API, ensuring type safety and providing default values for optional
fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SlackDecisionProperties(BaseModel):
    """Properties for a Decision entity sourced from a Slack message."""

    model_config = ConfigDict(extra="allow")

    text: str = Field(max_length=4000)
    channel_id: str
    channel_name: str | None = None
    user_id: str
    user_name: str | None = None
    timestamp: str  # Slack message ts
    thread_ts: str | None = None
    slack_link: str | None = None
    reaction_type: str | None = None  # The emoji that marked this as a decision


class SlackMentionProperties(BaseModel):
    """Properties for a Document entity sourced from a Slack mention context."""

    model_config = ConfigDict(extra="allow")

    channel_id: str
    channel_name: str | None = None
    timestamp: str
    text_preview: str | None = Field(None, max_length=500)
    mentioned_entity_ids: list[str] = Field(default_factory=list)
    user_id: str | None = None
    user_name: str | None = None


class SlackUserProperties(BaseModel):
    """Properties for a Person entity sourced from a Slack user."""

    model_config = ConfigDict(extra="allow")

    email: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    avatar_url: str | None = None
    title: str | None = None
    team_id: str | None = None
    is_bot: bool = False
    timezone: str | None = None
