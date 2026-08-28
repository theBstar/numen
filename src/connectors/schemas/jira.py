"""Pydantic schemas for Jira entity properties.

Validates properties stored on entities ingested from the Atlassian Cloud
Jira REST API v3.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JiraIssueProperties(BaseModel):
    """Properties for a Task entity sourced from a Jira issue."""

    model_config = ConfigDict(extra="allow")

    key: str  # e.g. "ENG-4521"
    summary: str
    description: str | None = None
    issue_type: str | None = None  # "Bug", "Story", "Task", "Epic", "Sub-task"
    priority: str | None = None  # "Highest", "High", "Medium", "Low", "Lowest"
    status_name: str | None = None  # e.g. "In Progress"
    status_category: str | None = None  # "new", "indeterminate", "done"
    assignee_email: str | None = None
    assignee_name: str | None = None
    reporter_email: str | None = None
    reporter_name: str | None = None
    project_key: str | None = None
    project_name: str | None = None
    labels: list[str] = Field(default_factory=list)
    components: list[str] = Field(default_factory=list)
    due_date: str | None = None
    url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # Backward-compat mirror of status_name for the urgency module / UI.
    state: str | None = None


class JiraProjectProperties(BaseModel):
    """Properties for a Feature entity sourced from a Jira project."""

    model_config = ConfigDict(extra="allow")

    key: str
    name: str
    project_type_key: str | None = None  # "software", "service_desk", "business"
    description: str | None = None
    lead_account_id: str | None = None
    lead_name: str | None = None
    url: str | None = None


class JiraUserProperties(BaseModel):
    """Properties for a Person entity sourced from a Jira user (account)."""

    model_config = ConfigDict(extra="allow")

    account_id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    active: bool = True
    account_type: str | None = None  # "atlassian", "app", "customer"
