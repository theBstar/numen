"""Pydantic schemas for Linear entity properties.

These models validate properties stored on entities ingested from the Linear
GraphQL API, ensuring type safety and providing default values for optional
fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LinearIssueProperties(BaseModel):
    """Properties for a Task entity sourced from a Linear issue."""

    model_config = ConfigDict(extra="allow")

    identifier: str  # e.g. "ENG-4521"
    title: str
    description: str | None = None
    priority: int | None = None  # Linear uses 0 (no priority) to 4 (urgent)
    priority_label: str | None = None  # "Urgent", "High", "Medium", "Low", "No priority"
    state_name: str | None = None  # e.g. "In Progress"
    state_type: str | None = (
        None  # "triage", "backlog", "unstarted", "started", "completed", "cancelled"
    )
    assignee_email: str | None = None
    assignee_name: str | None = None
    team_key: str | None = None
    team_name: str | None = None
    labels: list[str] = Field(default_factory=list)
    cycle_number: int | None = None
    estimate: float | None = None
    due_date: str | None = None
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # Backward compat - mapped from state_name for v1 callers
    state: str | None = None


class LinearProjectProperties(BaseModel):
    """Properties for a Feature entity sourced from a Linear project."""

    model_config = ConfigDict(extra="allow")

    name: str
    description: str | None = None
    state: str | None = None  # "planned", "started", "paused", "completed", "cancelled"
    start_date: str | None = None
    target_date: str | None = None
    lead_id: str | None = None
    lead_name: str | None = None
    progress: float | None = None
    url: str | None = None


class LinearUserProperties(BaseModel):
    """Properties for a Person entity sourced from a Linear user."""

    model_config = ConfigDict(extra="allow")

    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    active: bool = True
    role: str | None = None  # "admin", "member", "guest"
