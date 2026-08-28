"""Pydantic schemas for GitHub entity properties.

These models validate properties stored on entities ingested from the GitHub
REST API, ensuring type safety and providing default values for optional
fields.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GitHubPRProperties(BaseModel):
    """Properties for a Commit_PR entity sourced from a GitHub pull request."""

    model_config = ConfigDict(extra="allow")

    repo: str  # "owner/repo"
    number: int
    title: str
    body: str | None = None
    state: str  # "open", "closed"
    draft: bool = False
    merged: bool = False
    merged_at: str | None = None
    head_branch: str | None = None
    base_branch: str | None = None
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None
    html_url: str | None = None
    author: str | None = None
    author_email: str | None = None
    reviews_pending: int | None = None
    review_state: str | None = None  # "approved", "changes_requested", "commented", "pending"
    requested_reviewers: list[str] | None = None
    commit_messages: list[str] | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitHubDeploymentProperties(BaseModel):
    """Properties for a Deploy entity sourced from a GitHub deployment."""

    model_config = ConfigDict(extra="allow")

    repo: str
    environment: str  # "production", "staging", "preview"
    sha: str
    ref: str | None = None
    task: str | None = None
    description: str | None = None
    status: str | None = None  # "success", "failure", "error", "inactive", "pending", "in_progress"
    creator_login: str | None = None
    html_url: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class GitHubContributorProperties(BaseModel):
    """Properties for a Person entity sourced from a GitHub contributor."""

    model_config = ConfigDict(extra="allow")

    login: str
    email: str | None = None
    name: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    contributions: int | None = None
    role: str | None = None
