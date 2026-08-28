"""Pydantic schemas for Google Docs entity properties."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class GDocsDocumentProperties(BaseModel):
    """Properties for a Document entity sourced from a Google Doc."""

    model_config = ConfigDict(extra="allow")

    title: str
    url: str | None = None
    created_time: str | None = None
    modified_time: str | None = None
    chunk_count: int = 0
    chunks: list[dict] = Field(default_factory=list)
    mime_type: str | None = None
    owners: list[str] = Field(default_factory=list)
