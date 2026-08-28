"""Pydantic schemas for Notion entity properties."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NotionPageProperties(BaseModel):
    """Properties for a Document entity sourced from a Notion page."""

    model_config = ConfigDict(extra="allow")

    title: str
    url: str | None = None
    created_time: str | None = None
    last_edited_time: str | None = None
    archived: bool = False
    chunk_count: int = 0
    chunks: list[dict] = Field(default_factory=list)
    parent_type: str | None = None
    parent_id: str | None = None
