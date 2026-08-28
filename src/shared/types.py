"""Canonical types shared across all Numen modules."""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Enums ──────────────────────────────────────────────────────────────


class EntityType(str, enum.Enum):
    PERSON = "person"
    TASK = "task"
    COMMIT_PR = "commit_pr"
    DEPLOY = "deploy"
    INCIDENT = "incident"
    ERROR_EVENT = "error_event"
    METRIC_SNAPSHOT = "metric_snapshot"
    FEATURE = "feature"
    GOAL = "goal"
    DOCUMENT = "document"
    DECISION = "decision"
    PROJECT = "project"
    SPRINT = "sprint"


class CoreType(str, enum.Enum):
    PERSON = "person"
    TEAM = "team"
    GOAL = "goal"
    DECISION = "decision"
    DOCUMENT = "document"
    SIGNAL = "signal"
    METRIC_SNAPSHOT = "metric_snapshot"
    COMMUNICATION = "communication"
    WORK_ITEM = "work_item"
    ARTIFACT = "artifact"


class Domain(str, enum.Enum):
    ENGINEERING = "engineering"
    PRODUCT = "product"
    DESIGN = "design"
    SUPPORT = "support"
    SALES = "sales"
    FINANCE = "finance"
    OPS = "ops"
    CORE = "core"


class EdgeType(str, enum.Enum):
    OWNS = "owns"
    BLOCKS = "blocks"
    DEPENDS_ON = "depends_on"
    AUTHORED = "authored"
    MENTIONED_IN = "mentioned_in"
    SHIPS_TO = "ships_to"
    MEASURES = "measures"
    CAUSED_BY = "caused_by"
    TAGGED_TO = "tagged_to"
    CONFLICTS_WITH = "conflicts_with"
    CONTAINS = "contains"
    PARENT_OF = "parent_of"
    ASSIGNED_TO = "assigned_to"
    REPORTS_TO = "reports_to"
    MEMBER_OF = "member_of"
    SURFACED_TO = "surfaced_to"
    ACTED_ON = "acted_on"
    DISMISSED = "dismissed"
    APPROVED_BY = "approved_by"
    ESCALATED_TO = "escalated_to"
    PRECEDED_BY = "preceded_by"
    REVIEWS = "reviews"
    DEPLOYED_BY = "deployed_by"
    # PRD-specific edges
    REFERENCES = "references"
    STAKEHOLDER_OF = "stakeholder_of"
    REVIEWER_OF = "reviewer_of"
    IMPLEMENTS = "implements"
    DESIGNS_FOR = "designs_for"
    SECTION_LINKS_TO = "section_links_to"


class SourceType(str, enum.Enum):
    LINEAR = "linear"
    GITHUB = "github"
    SLACK = "slack"
    JIRA = "jira"
    NOTION = "notion"
    GDOCS = "gdocs"
    DATADOG = "datadog"
    SENTRY = "sentry"
    PAGERDUTY = "pagerduty"
    AMPLITUDE = "amplitude"
    POSTHOG = "posthog"
    FIGMA = "figma"
    MANUAL = "manual"


class RoleType(str, enum.Enum):
    ENGINEER = "engineer"
    PM = "pm"
    EM = "em"
    CTO = "cto"
    VP_ENG = "vp_eng"
    VP_PRODUCT = "vp_product"
    DESIGNER = "designer"


class SyncStatus(str, enum.Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    ERROR = "error"


class DeliveryStatus(str, enum.Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class GoalLevel(str, enum.Enum):
    """Hierarchy level for goals/OKRs."""

    COMPANY = "company"
    TEAM = "team"
    INDIVIDUAL = "individual"


class TaskStatus(str, enum.Enum):
    """Task lifecycle status."""

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    MERGED = "merged"
    DONE = "done"
    ARCHIVED = "archived"


# Ordered pipeline for forward-only task transitions (PR state -> task status).
# Does not include BACKLOG or ARCHIVED which are outside the main flow.
TASK_STATUS_PIPELINE = [
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.IN_REVIEW,
    TaskStatus.MERGED,
    TaskStatus.DONE,
]


class ProjectStatus(str, enum.Enum):
    """Project lifecycle status."""

    PLANNING = "planning"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class PrdStatus(str, enum.Enum):
    """PRD document lifecycle status (forward-only)."""

    IDEA = "idea"
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    NEEDS_REVISION = "needs_revision"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    SHIPPED = "shipped"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


# Ordered pipeline for PRD lifecycle transitions.
PRD_STATUS_PIPELINE = [
    PrdStatus.IDEA,
    PrdStatus.DRAFT,
    PrdStatus.IN_REVIEW,
    PrdStatus.APPROVED,
    PrdStatus.IN_PROGRESS,
    PrdStatus.SHIPPED,
]


class PrdNodeType(str, enum.Enum):
    """Type of node in the PRD folder tree."""

    FOLDER = "folder"
    DOCUMENT = "document"
    IMAGE = "image"


class PrdReviewStatus(str, enum.Enum):
    """Status of a PRD review."""

    PENDING = "pending"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"


class Priority(str, enum.Enum):
    """Priority level for tasks and projects."""

    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PersonResolutionStatus(str, enum.Enum):
    """Status of a person resolution suggestion."""

    PENDING = "pending"
    MERGED = "merged"
    DISTINCT = "distinct"
    DISMISSED = "dismissed"


class LinkSuggestionStatus(str, enum.Enum):
    """Status of a link suggestion."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ProgressMode(str, enum.Enum):
    """How goal progress is tracked."""

    MANUAL = "manual"
    COMPUTED = "computed"


class PRState(str, enum.Enum):
    """Pull request state."""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"
    DRAFT = "draft"


class SignalType(str, enum.Enum):
    """Briefing signal types for provenance tracking."""

    # Engineer / PM (existing)
    PR_REVIEW_REQUESTED = "pr_review_requested"
    BLOCKING_CHAIN = "blocking_chain"
    RECENT_INCIDENT = "recent_incident"
    BLOCKED_TASKS_PER_FEATURE = "blocked_tasks_per_feature"
    OPEN_DECISION = "open_decision"
    LOW_ADOPTION = "low_adoption"
    # EM signals
    IC_BLOCKED = "ic_blocked"
    STALLED_PR = "stalled_pr"
    ONE_ON_ONE_PREP = "one_on_one_prep"
    WIP_OVERLOAD = "wip_overload"
    # CTO signals
    ORG_BOTTLENECK = "org_bottleneck"
    AT_RISK_GOAL = "at_risk_goal"
    CROSS_TEAM_GAP = "cross_team_gap"
    # VP Eng signals
    TEAM_HEALTH = "team_health"
    SPRINT_STATE = "sprint_state"
    INCIDENT_RATE = "incident_rate"
    # VP Product signals
    GOAL_NO_COVERAGE = "goal_no_coverage"
    LAUNCH_BLOCKER = "launch_blocker"
    STALE_DECISION = "stale_decision"
    # Designer signals
    CONFLICTING_SPEC = "conflicting_spec"
    OVERDUE_REVIEW = "overdue_review"
    HANDOFF_READY = "handoff_ready"
    # PRD signals
    PRD_STALE = "prd_stale"
    PRD_SPEC_GAP = "prd_spec_gap"
    PRD_REVIEW_PENDING = "prd_review_pending"
    PRD_CONFLICT = "prd_conflict"


class Direction(str, enum.Enum):
    """Graph traversal direction."""

    OUTGOING = "outgoing"
    INCOMING = "incoming"
    BOTH = "both"


class ChatRole(str, enum.Enum):
    """Chat message role."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ── Living (agent fleet) types ────────────────────────────────────────


class AgentRuntime(str, enum.Enum):
    """Supported agent runtimes for Living tasks."""

    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    CURSOR = "cursor"


class LivingTaskStatus(str, enum.Enum):
    """Lifecycle status for a Living task."""

    QUEUED = "queued"
    SPAWNING = "spawning"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class LivingWorktreeStatus(str, enum.Enum):
    """Lifecycle status for a Living worktree."""

    PROVISIONING = "provisioning"
    READY = "ready"
    RUNNING = "running"
    DRAINING = "draining"
    ARCHIVED = "archived"


# State-machine for Living tasks. Maps current status -> set of legal targets.
# Per design doc: queued -> spawning -> running -> done|failed,
# queued -> cancelled, running -> cancelled.
LIVING_TASK_TRANSITIONS: dict[LivingTaskStatus, set[LivingTaskStatus]] = {
    LivingTaskStatus.QUEUED: {LivingTaskStatus.SPAWNING, LivingTaskStatus.CANCELLED},
    LivingTaskStatus.SPAWNING: {LivingTaskStatus.RUNNING, LivingTaskStatus.FAILED},
    LivingTaskStatus.RUNNING: {
        LivingTaskStatus.DONE,
        LivingTaskStatus.FAILED,
        LivingTaskStatus.CANCELLED,
    },
    LivingTaskStatus.DONE: set(),
    LivingTaskStatus.FAILED: set(),
    LivingTaskStatus.CANCELLED: set(),
}


def is_legal_living_task_transition(
    current: LivingTaskStatus, target: LivingTaskStatus
) -> bool:
    """Return True if `current -> target` is a legal Living task transition."""
    return target in LIVING_TASK_TRANSITIONS.get(current, set())


class LivingPrProvider(str, enum.Enum):
    """Where a Living task's changes were sent."""

    GITHUB = "github"
    LOCAL = "local"


class LivingPrState(str, enum.Enum):
    """Lifecycle of a Living task's pull request (or local merge)."""

    NONE = "none"
    DRAFT = "draft"
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class LivingMergeStateStatus(str, enum.Enum):
    """Mirror of GitHub's mergeStateStatus, plus 'unknown' for not-yet-polled."""

    UNKNOWN = "unknown"
    CLEAN = "clean"
    DIRTY = "dirty"
    BEHIND = "behind"
    BLOCKED = "blocked"
    HAS_HOOKS = "has_hooks"


class LivingMergeStrategy(str, enum.Enum):
    """How a Living task's changes were merged."""

    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


# ── Pydantic models (shared contracts between modules) ─────────────────


class EntityCreate(BaseModel):
    org_id: UUID
    type: EntityType
    source: SourceType
    source_ids: dict[str, str] = Field(default_factory=dict)
    canonical_name: str
    properties: dict = Field(default_factory=dict)


class EdgeCreate(BaseModel):
    org_id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    type: EdgeType
    weight: float = 1.0
    confidence: float = 1.0
    evidence: list[dict] = Field(default_factory=list)


class UrgencyScore(BaseModel):
    entity_id: UUID
    person_id: UUID
    org_id: UUID
    score: float
    components: dict = Field(default_factory=dict)
    goal_ids: list[UUID] = Field(default_factory=list)
    provenance: list[dict] = Field(default_factory=list)
    computed_at: datetime


class BriefingItem(BaseModel):
    entity_id: UUID
    entity_type: EntityType
    title: str
    why_it_matters: str
    urgency_score: float
    goal_tags: list[str] = Field(default_factory=list)
    source_links: list[dict] = Field(default_factory=list)
    suggested_action: str | None = None
    provenance: list[dict] = Field(default_factory=list)


class ConnectorSyncResult(BaseModel):
    source: SourceType
    entities_created: int = 0
    entities_updated: int = 0
    edges_created: int = 0
    edges_updated: int = 0
    errors: list[str] = Field(default_factory=list)
