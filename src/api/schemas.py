"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from src.shared.types import (
    DeliveryStatus,
    EdgeType,
    EntityType,
    RoleType,
    SourceType,
    SyncStatus,
    TaskStatus,
)

# ── Pagination ─────────────────────────────────────────────────────────


class PaginatedResponse(BaseModel):
    items: list = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 50


# ── Entity responses ───────────────────────────────────────────────────


class EntityResponse(BaseModel):
    id: UUID
    org_id: UUID
    type: EntityType
    source: SourceType
    source_ids: dict[str, str]
    canonical_name: str
    properties: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EdgeResponse(BaseModel):
    id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    type: EdgeType
    weight: float
    confidence: float
    first_seen_at: datetime
    last_active_at: datetime

    model_config = {"from_attributes": True}


class EntityDetailResponse(BaseModel):
    entity: EntityResponse
    edges: list[EdgeResponse] = Field(default_factory=list)


class EntityListResponse(PaginatedResponse):
    items: list[EntityResponse] = Field(default_factory=list)


# ── Urgency responses ──────────────────────────────────────────────────


class UrgencyScoreResponse(BaseModel):
    entity_id: UUID
    entity_name: str = ""
    entity_type: EntityType | None = None
    score: float
    score_components: dict = Field(default_factory=dict)
    goal_ids: list[UUID] = Field(default_factory=list)
    provenance: list[dict] = Field(default_factory=list)
    computed_at: datetime

    model_config = {"from_attributes": True}


class UrgencyListResponse(BaseModel):
    items: list[UrgencyScoreResponse] = Field(default_factory=list)
    person_id: UUID | None = None
    role: RoleType | None = None


class ScoringTraceResponse(BaseModel):
    """Detailed trace for a single urgency scoring factor."""

    factor_name: str
    weight: float
    raw_value: float
    weighted_value: float
    explanation: str
    evidence: list[dict] = Field(default_factory=list)


class UrgencyTraceResponse(BaseModel):
    """Full scoring trace for an entity's urgency score."""

    entity_id: str
    entity_name: str = ""
    score: float
    scoring_traces: list[ScoringTraceResponse] = Field(default_factory=list)
    computed_at: str


# ── Briefing responses ─────────────────────────────────────────────────


class BriefingItemResponse(BaseModel):
    entity_id: UUID
    entity_type: EntityType
    title: str
    why_it_matters: str
    urgency_score: float
    goal_tags: list[str] = Field(default_factory=list)
    source_links: list[dict] = Field(default_factory=list)
    suggested_action: str | None = None
    provenance: list[dict] = Field(default_factory=list)


class BriefingResponse(BaseModel):
    id: UUID
    org_member_id: UUID
    generated_at: datetime
    items: list[BriefingItemResponse] = Field(default_factory=list)
    empty_reason: str | None = None
    delivery_status: DeliveryStatus
    delivered_at: datetime | None = None

    model_config = {"from_attributes": True}


class BriefingListResponse(PaginatedResponse):
    items: list[BriefingResponse] = Field(default_factory=list)


class TestBriefingResponse(BaseModel):
    """Result of POST /briefings/test - a one-shot test send via the user's chosen channel."""

    channel: Literal["email", "slack"]
    delivered: bool
    fallback_reason: str | None = None
    item_count: int
    message: str


# ── Goal requests/responses ────────────────────────────────────────────


class KeyResultInput(BaseModel):
    """A single key result within a goal."""

    title: str
    target_value: float = 100.0
    current_value: float = 0.0
    unit: str = "%"


class GoalCreateRequest(BaseModel):
    """Request body for creating a goal entity."""

    title: str = Field(..., min_length=1, max_length=512)
    level: str = Field(
        default="team",
        description="Goal hierarchy level: company, team, or individual",
        pattern="^(company|team|individual)$",
    )
    key_results: list[KeyResultInput] = Field(default_factory=list)
    target_value: float | None = Field(
        default=None, description="Overall target value for the goal"
    )
    owner_email: str | None = Field(default=None, description="Email of the goal owner")
    parent_goal_id: UUID | None = Field(
        default=None, description="UUID of the parent goal for hierarchy"
    )
    time_bound_start: datetime | None = Field(
        default=None, description="Start of the goal time window (ISO 8601)"
    )
    time_bound_end: datetime | None = Field(
        default=None, description="End of the goal time window (ISO 8601)"
    )


class GoalUpdateRequest(BaseModel):
    """Request body for updating a goal. All fields optional for partial update."""

    title: str | None = Field(default=None, min_length=1, max_length=512)
    level: str | None = Field(
        default=None,
        pattern="^(company|team|individual)$",
    )
    key_results: list[KeyResultInput] | None = None
    target_value: float | None = None
    current_value: float | None = None
    owner_email: str | None = None
    parent_goal_id: UUID | None = None
    time_bound_start: datetime | None = None
    time_bound_end: datetime | None = None
    status: str | None = Field(
        default=None,
        pattern="^(active|archived)$",
        description="Set to 'archived' for soft delete, or 'active' to restore",
    )


class GoalResponse(BaseModel):
    """Response model for a goal entity."""

    id: UUID
    title: str
    level: str
    status: str
    key_results: list[dict] = Field(default_factory=list)
    target_value: float | None = None
    current_value: float | None = None
    computed_progress: float | None = Field(
        default=None,
        description="Progress percentage computed from linked tasks (0-100)",
    )
    owner: str | None = None
    parent_goal_id: UUID | None = None
    child_goal_ids: list[UUID] = Field(default_factory=list)
    linked_project_ids: list[UUID] = Field(default_factory=list)
    time_bound_start: datetime | None = None
    time_bound_end: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GoalProgressResponse(BaseModel):
    """Computed progress for a goal based on linked tasks."""

    goal_id: UUID
    total_tasks: int = 0
    tasks_done: int = 0
    computed_progress: float = Field(
        default=0.0,
        description="Percentage of linked tasks completed (0-100)",
    )
    key_results_progress: list[dict] = Field(
        default_factory=list,
        description=(
            "Progress per key result: [{title, target_value, current_value, unit, progress_pct}]"
        ),
    )


class GoalListResponse(BaseModel):
    items: list[GoalResponse] = Field(default_factory=list)


class GoalTreeResponse(BaseModel):
    items: list = Field(default_factory=list)


class GoalLinkRequest(BaseModel):
    """Request body for linking a goal to another entity."""

    entity_id: UUID = Field(..., description="UUID of the entity to link to this goal")


# ── Connector status ───────────────────────────────────────────────────


class ConnectorStatusResponse(BaseModel):
    connector: SourceType
    connected: bool
    last_sync_at: datetime | None = None
    status: SyncStatus = SyncStatus.IDLE
    error_message: str | None = None
    # True when the stored token is missing scopes that newer features require
    # (e.g. Slack briefing DMs need chat:write/im:write). The frontend prompts
    # the user to reconnect.
    needs_reauth: bool = False


class ConnectorListResponse(BaseModel):
    items: list[ConnectorStatusResponse] = Field(default_factory=list)


class GitHubRepoResponse(BaseModel):
    full_name: str
    name: str
    owner: str
    private: bool
    description: str | None = None
    enabled: bool = False


class GitHubRepoListResponse(BaseModel):
    repos: list[GitHubRepoResponse] = Field(default_factory=list)


class ConnectorSettingsUpdateRequest(BaseModel):
    selected_repos: list[str] = Field(default_factory=list)


class ConnectorSettingsResponse(BaseModel):
    selected_repos: list[str] = Field(default_factory=list)
    webhook_ids: dict[str, int] = Field(default_factory=dict)


class SyncTriggerResponse(BaseModel):
    status: str = "ok"
    entities_created: int = 0
    entities_updated: int = 0
    edges_created: int = 0
    edges_updated: int = 0
    errors: list[str] = Field(default_factory=list)


# ── Organization ───────────────────────────────────────────────────────


class OrgListResponse(BaseModel):
    items: list["OrgResponse"] = Field(default_factory=list)


class OnboardingRequest(BaseModel):
    display_name: str
    role: str = "engineer"
    org_name: str
    org_slug: str


class OrgCreateRequest(BaseModel):
    name: str
    slug: str


class OrgResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_demo: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class MemberListResponse(BaseModel):
    items: list["MemberResponse"] = Field(default_factory=list)


class MemberCreateRequest(BaseModel):
    email: str
    display_name: str | None = None
    role: RoleType = RoleType.ENGINEER
    timezone: str = "America/New_York"


class MemberUpdateRequest(BaseModel):
    role: RoleType | None = None
    display_name: str | None = None
    timezone: str | None = None
    briefing_hour: int | None = None
    briefing_channel: Literal["email", "slack"] | None = None

    @field_validator("briefing_hour")
    @classmethod
    def _validate_hour(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not 0 <= v <= 23:
            raise ValueError("briefing_hour must be between 0 and 23")
        return v


class MemberResponse(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    display_name: str | None = None
    role: RoleType
    timezone: str
    person_entity_id: UUID | None = None
    created_at: datetime
    briefing_hour: int = 8
    briefing_channel: Literal["email", "slack"] = "email"

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _flatten_preferences(cls, data: Any) -> Any:
        if not hasattr(data, "preferences"):
            return data
        prefs = getattr(data, "preferences", None) or {}
        values = {
            "id": data.id,
            "org_id": data.org_id,
            "email": data.email,
            "display_name": data.display_name,
            "role": data.role,
            "timezone": data.timezone,
            "person_entity_id": data.person_entity_id,
            "created_at": data.created_at,
            "briefing_hour": prefs.get("briefing_hour", 8),
            "briefing_channel": prefs.get("briefing_channel", "email"),
        }
        return values


# ── Claude dispatch ────────────────────────────────────────────────────


class ClaudeDispatchRequest(BaseModel):
    action: str  # "summarize_pr_diff"
    entity_id: UUID


class ClaudeDispatchResponse(BaseModel):
    action: str
    entity_id: UUID
    result: dict
    draft: bool = True


# ── API keys (MCP) ───────────────────────────────────────────────────


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)


class ApiKeyCreateResponse(BaseModel):
    id: UUID
    name: str
    key: str = Field(description="Plaintext API key - shown only once")
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: UUID
    name: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyResponse] = Field(default_factory=list)


# ── Task transition preview ──────────────────────────────────────────


class TransitionPreviewResponse(BaseModel):
    should_transition: bool
    current_status: str
    target_status: str
    pr_name: str
    task_name: str


# ── AI prompt generation ─────────────────────────────────────────────


class AiPromptResponse(BaseModel):
    prompt: str
    raw_prompt: str
    task_title: str
    repo_urls: list[str] = Field(default_factory=list)
    has_blocking_chain: bool = False
    goal_count: int = 0
    llm_trace: dict | None = None


# ── Edge requests ─────────────────────────────────────────────────────


class EdgeCreateRequest(BaseModel):
    from_entity_id: UUID
    to_entity_id: UUID
    type: EdgeType
    weight: float = 1.0
    skip_auto_transition: bool = False


class EdgeDeleteRequest(BaseModel):
    from_entity_id: UUID
    to_entity_id: UUID
    type: EdgeType


class EdgeListResponse(BaseModel):
    items: list[EdgeResponse] = Field(default_factory=list)


# ── Graph neighborhood ─────────────────────────────────────────────────


class GraphNeighborhoodResponse(BaseModel):
    entities: list[EntityResponse] = Field(default_factory=list)
    edges: list[EdgeResponse] = Field(default_factory=list)


class FullGraphResponse(BaseModel):
    """Full org context graph with pagination."""

    entities: list[EntityResponse] = Field(default_factory=list)
    edges: list[EdgeResponse] = Field(default_factory=list)
    total_entities: int = 0
    total_edges: int = 0
    has_more: bool = False


# ── Task requests/responses ───────────────────────────────────────────


class TaskCreateRequest(BaseModel):
    title: str
    description: str | None = None
    status: str = TaskStatus.TODO
    priority: str = "medium"
    assignee_email: str | None = None
    due_date: date | None = None
    project_id: UUID | None = None
    goal_ids: list[UUID] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    story_points: int | None = None
    estimated_hours: float | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: str | None = None
    priority: str | None = None
    assignee_email: str | None = None
    due_date: date | None = None
    project_id: UUID | None = None
    goal_ids: list[UUID] | None = None
    labels: list[str] | None = None
    story_points: int | None = None
    estimated_hours: float | None = None


class TaskResponse(BaseModel):
    id: UUID
    title: str
    description: str | None = None
    status: str
    priority: str
    assignee: str | None = None
    due_date: date | None = None
    source: SourceType
    project_id: UUID | None = None
    goal_ids: list[UUID] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    story_points: int | None = None
    estimated_hours: float | None = None
    parent_id: UUID | None = None
    subtask_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(PaginatedResponse):
    items: list[TaskResponse] = Field(default_factory=list)


class TaskLinkRequest(BaseModel):
    entity_id: UUID
    edge_type: EdgeType


# -- Projects ---------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = Field(None, max_length=4096)
    status: str = Field("planning")
    owner_email: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    goal_ids: list[UUID] = Field(default_factory=list)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    status: str | None = None
    owner_email: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    goal_ids: list[UUID] | None = None


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    status: str
    owner: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    task_count: int = 0
    tasks_done: int = 0
    goal_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(PaginatedResponse):
    items: list[ProjectResponse] = Field(default_factory=list)


class ProjectTaskListResponse(BaseModel):
    items: list[TaskResponse] = Field(default_factory=list)


# ── Chat ──────────────────────────────────────────────────────────────


class ConversationResponse(BaseModel):
    id: UUID
    title: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    tool_calls: list[dict] | None = None
    referenced_entities: list[dict] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSendRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=4096)


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse] = Field(default_factory=list)


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse] = Field(default_factory=list)


# ── People / Org graph ────────────────────────────────────────────────


class PersonCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    email: str | None = None
    role: RoleType = RoleType.ENGINEER
    title: str | None = Field(default=None, description="Job title")
    manager_id: UUID | None = Field(
        default=None, description="Person entity ID of the manager (creates REPORTS_TO edge)"
    )


class PersonResponse(BaseModel):
    id: UUID
    name: str
    email: str | None = None
    role: str | None = None
    title: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class OrgGraphResponse(BaseModel):
    """People with their reporting edges for building an org tree."""

    people: list[EntityResponse] = Field(default_factory=list)
    edges: list[EdgeResponse] = Field(default_factory=list)


# ── Person resolution ─────────────────────────────────────────────────


class PersonResolutionResponse(BaseModel):
    id: UUID
    candidate: EntityResponse
    match: EntityResponse
    confidence: float
    match_reasons: list[dict] = Field(default_factory=list)
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PersonResolutionListResponse(BaseModel):
    items: list[PersonResolutionResponse] = Field(default_factory=list)


class PersonResolutionCountResponse(BaseModel):
    pending: int = 0


class ResolutionLinkRequest(BaseModel):
    target_entity_id: UUID


# ── Link suggestions ──────────────────────────────────────────────────


class LinkSuggestionResponse(BaseModel):
    id: UUID
    source_entity: EntityResponse
    target_entity: EntityResponse
    edge_type: EdgeType
    confidence: float
    reasoning: str | None = None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class LinkSuggestionListResponse(BaseModel):
    items: list[LinkSuggestionResponse] = Field(default_factory=list)


class LinkSuggestionCountResponse(BaseModel):
    pending: int = 0


# ── Task Activity ─────────────────────────────────────────────────────


class TaskActivityResponse(BaseModel):
    id: UUID
    entity_id: UUID
    activity_type: str
    actor_id: UUID | None = None
    actor_name: str | None = None
    content: str | None = None
    details: dict = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskActivityListResponse(BaseModel):
    items: list[TaskActivityResponse] = Field(default_factory=list)


class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class CommentUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


# ── Subtasks ──────────────────────────────────────────────────────────


class SubtaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=512)
    description: str | None = None
    priority: str = "medium"
    assignee_email: str | None = None
    due_date: date | None = None
    labels: list[str] = Field(default_factory=list)


# ── Saved Views ───────────────────────────────────────────────────────


class SavedViewCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    entity_type: str = "task"
    filters: dict = Field(default_factory=dict)
    sort_config: dict = Field(default_factory=dict)
    view_mode: str = "list"
    group_by: str | None = None
    is_default: bool = False
    is_shared: bool = False


class SavedViewUpdateRequest(BaseModel):
    name: str | None = None
    filters: dict | None = None
    sort_config: dict | None = None
    view_mode: str | None = None
    group_by: str | None = None
    is_default: bool | None = None
    is_shared: bool | None = None


class SavedViewResponse(BaseModel):
    id: UUID
    name: str
    entity_type: str
    filters: dict = Field(default_factory=dict)
    sort_config: dict = Field(default_factory=dict)
    view_mode: str = "list"
    group_by: str | None = None
    is_default: bool = False
    is_shared: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SavedViewListResponse(BaseModel):
    items: list[SavedViewResponse] = Field(default_factory=list)


# ── Kanban Settings ───────────────────────────────────────────────────


class KanbanSettingItem(BaseModel):
    column_status: str
    wip_limit: int | None = None


class KanbanSettingsUpdateRequest(BaseModel):
    items: list[KanbanSettingItem] = Field(default_factory=list)


class KanbanSettingsResponse(BaseModel):
    items: list[KanbanSettingItem] = Field(default_factory=list)


# ── Sprints ───────────────────────────────────────────────────────────


class SprintCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    start_date: date | None = None
    end_date: date | None = None
    goal: str | None = None
    velocity_target: int | None = None


class SprintUpdateRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    goal: str | None = None
    velocity_target: int | None = None


class SprintResponse(BaseModel):
    id: UUID
    name: str
    status: str = "planning"
    start_date: date | None = None
    end_date: date | None = None
    goal: str | None = None
    velocity_target: int | None = None
    task_count: int = 0
    story_points_total: int = 0
    story_points_done: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SprintListResponse(BaseModel):
    items: list[SprintResponse] = Field(default_factory=list)


class SprintAddTasksRequest(BaseModel):
    task_ids: list[UUID] = Field(..., min_length=1)


# ── Task Templates ────────────────────────────────────────────────────


class TaskTemplateCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    default_properties: dict = Field(default_factory=dict)
    subtask_titles: list[str] = Field(default_factory=list)


class TaskTemplateUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    default_properties: dict | None = None
    subtask_titles: list[str] | None = None


class TaskTemplateResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    default_properties: dict = Field(default_factory=dict)
    subtask_titles: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskTemplateListResponse(BaseModel):
    items: list[TaskTemplateResponse] = Field(default_factory=list)


# ── Notifications ─────────────────────────────────────────────────────


class NotificationResponse(BaseModel):
    id: UUID
    type: str
    entity_id: UUID | None = None
    actor_id: UUID | None = None
    actor_name: str | None = None
    title: str
    details: dict = Field(default_factory=dict)
    read_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(default_factory=list)


class NotificationUnreadCountResponse(BaseModel):
    count: int = 0


# ── Attachments ───────────────────────────────────────────────────────


class AttachmentResponse(BaseModel):
    id: UUID
    entity_id: UUID
    filename: str
    file_size: int | None = None
    mime_type: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachmentListResponse(BaseModel):
    items: list[AttachmentResponse] = Field(default_factory=list)


# ── Error responses ───────────────────────────────────────────────────


class ErrorResponse(BaseModel):
    detail: str


class ValidationErrorDetail(BaseModel):
    loc: list[str | int]
    msg: str
    type: str


class ValidationErrorResponse(BaseModel):
    detail: list[ValidationErrorDetail]


# ── Status / Health responses ─────────────────────────────────────────


class StatusResponse(BaseModel):
    status: str = "ok"
    message: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"


class RootResponse(BaseModel):
    app: str = "numen"
    version: str = "0.1.0"
    docs: str = "/docs"


# ── Auth responses ────────────────────────────────────────────────────


class OAuthConnectResponse(BaseModel):
    redirect_url: str


class OAuthCallbackResponse(BaseModel):
    status: str = "ok"
    connector: str
    org_id: str


class OAuthDisconnectResponse(BaseModel):
    status: str = "ok"
    connector: str


class WebhookResponse(BaseModel):
    status: str = "ok"
    processed: bool = True


# ── Goal link responses ───────────────────────────────────────────────


class GoalLinkResponse(BaseModel):
    status: str = "ok"
    goal_id: str
    entity_id: str
    edge_type: str


class GoalUnlinkResponse(BaseModel):
    status: str = "ok"
    goal_id: str
    entity_id: str


# ── Dashboard summary ──────────────────────────────────────────────


class TaskCountsResponse(BaseModel):
    active: int = 0
    in_review: int = 0
    todo: int = 0
    blocked: int = 0
    total: int = 0


class TeamMemberWorkload(BaseModel):
    person_id: str
    person_name: str
    todo: int = 0
    in_progress: int = 0
    in_review: int = 0
    done: int = 0
    total: int = 0


class DelayedProjectItem(BaseModel):
    id: str
    name: str
    days_overdue: int = 0
    remaining_tasks: int = 0


class GoalsSummary(BaseModel):
    total: int = 0
    on_track: int = 0
    at_risk: int = 0
    no_coverage: int = 0


class DashboardSummaryResponse(BaseModel):
    role: RoleType
    my_tasks: TaskCountsResponse = Field(default_factory=TaskCountsResponse)
    pr_reviews_pending: int = 0
    goals_summary: GoalsSummary | None = None
    team_workload: list[TeamMemberWorkload] | None = None
    team_size: int = 0
    delayed_projects: list[DelayedProjectItem] | None = None
    stalled_prs_count: int = 0
    cross_team_blocks: int = 0
    recent_incidents_count: int = 0
