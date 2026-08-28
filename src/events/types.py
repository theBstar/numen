"""Domain event types emitted by connectors and consumed by handlers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.types import ConnectorSyncResult, EdgeType, EntityType, SourceType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class EntityUpserted:
    """Emitted after an entity is created or updated.

    Handlers react to entity_type (not source), so the same handler fires
    for GitHub PRs, GitLab MRs, or any future connector.
    """

    db: AsyncSession
    org_id: UUID
    entity_id: UUID
    entity_type: EntityType
    source: SourceType
    was_created: bool
    properties: dict


@dataclass(frozen=True, slots=True)
class SyncCompleted:
    """Emitted after any connector sync (full, delta, or webhook) completes."""

    db: AsyncSession
    org_id: UUID
    source: SourceType
    result: ConnectorSyncResult


@dataclass(frozen=True, slots=True)
class EdgeCreated:
    """Emitted after an edge is created via API (manual link or suggestion acceptance)."""

    db: AsyncSession
    org_id: UUID
    from_entity_id: UUID
    to_entity_id: UUID
    edge_type: EdgeType
    skip_auto_transition: bool = False


@dataclass(frozen=True, slots=True)
class BriefingRequested:
    """Emitted before briefing assembly to trigger pre-computation."""

    db: AsyncSession
    org_id: UUID
    member_id: UUID


@dataclass(frozen=True, slots=True)
class PrdContentChanged:
    """Emitted after PRD blocks are created, updated, or deleted."""

    db: AsyncSession
    org_id: UUID
    entity_id: UUID
    changed_block_ids: list[UUID]
    changed_by: UUID  # member_id


@dataclass(frozen=True, slots=True)
class LivingTaskEvent:
    """Generic Living task lifecycle event ingested from the Mac app."""

    db: AsyncSession
    org_id: UUID
    task_id: UUID
    kind: str
    payload: dict
    agent_id: UUID | None = None
    worktree_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class PrdStatusChanged:
    """Emitted after a PRD transitions to a new lifecycle status."""

    db: AsyncSession
    org_id: UUID
    entity_id: UUID
    old_status: str
    new_status: str
    changed_by: UUID  # member_id


# ── Living spike events ──────────────────────────────────────────────
#
# All Living events share a common shape: org_id, task_id, agent_id, ts,
# plus an event-specific payload. They are persisted by
# ``LivingEventPersistenceHandler`` (events/handlers.py) to the
# ``living_event`` table for replay/analytics. The bus contract is
# preserved: a DB write failure logs but does not abort the emitter.


@dataclass(frozen=True, slots=True)
class _LivingEventBase:
    db: AsyncSession
    org_id: UUID
    task_id: UUID | None = None
    agent_id: UUID | None = None
    ts: datetime = field(default_factory=_utcnow)


@dataclass(frozen=True, slots=True)
class ContextFetchEvent(_LivingEventBase):
    """Agent invoked MCP ``get_context`` for a task."""

    task_query: str = ""
    top_k_doc_ids: tuple[str, ...] = ()
    total_tokens: int = 0
    result_count: int = 0
    worktree_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SessionStartEvent(_LivingEventBase):
    """Agent session began for a task (subprocess spawned + handshake)."""

    runtime: str = ""  # claude_code, codex, cursor
    worktree_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class SessionCompleteEvent(_LivingEventBase):
    """Agent session ended (success, failure, or cancellation)."""

    runtime: str = ""
    exit_code: int | None = None
    duration_seconds: float | None = None
    worktree_id: UUID | None = None
    outcome: str = "done"  # done, failed, cancelled


@dataclass(frozen=True, slots=True)
class WorktreeSpawnEvent(_LivingEventBase):
    """A new git worktree was provisioned for a task."""

    worktree_id: UUID | None = None
    fs_path: str = ""
    branch_name: str = ""


@dataclass(frozen=True, slots=True)
class WorktreeArchiveEvent(_LivingEventBase):
    """A worktree was archived/torn down."""

    worktree_id: UUID | None = None
    fs_path: str = ""
    reason: str = "ttl"  # ttl, user_close, error


@dataclass(frozen=True, slots=True)
class AgentInterventionEvent(_LivingEventBase):
    """User typed an intervention into the worktree's terminal pane."""

    worktree_id: UUID | None = None
    text: str = ""
    direction: str = "user_to_agent"  # or agent_to_user



# ── Living Ship/Merge events ─────────────────────────────────────────
#
# Emitted from /api/living/tasks/{id}/{branch-pushed,pull-request,merge}.


@dataclass(frozen=True, slots=True)
class BranchPushedEvent(_LivingEventBase):
    """Mac app pushed a worktree branch up to origin."""

    branch_name: str = ""
    commit_sha: str = ""


@dataclass(frozen=True, slots=True)
class PrStateChangedEvent(_LivingEventBase):
    """A Living task's pull request transitioned to a new state."""

    pr_state: str = "none"  # none|draft|open|merged|closed
    merge_state_status: str = "unknown"  # unknown|clean|dirty|behind|blocked|has_hooks
    pr_number: int | None = None


@dataclass(frozen=True, slots=True)
class MergeCompletedEvent(_LivingEventBase):
    """A Living task's changes were merged (PR or local)."""

    merge_strategy: str = "squash"  # merge|squash|rebase
    merged_commit_sha: str = ""
    provider: str = "github"  # github|local


@dataclass(frozen=True, slots=True)
class MergeFailedEvent(_LivingEventBase):
    """A merge attempt failed (gh exit non-zero, conflict, etc.)."""

    error: str = ""
    provider: str = "github"

# Tuple kept module-level so the handler module can iterate the full set
# without importing each name individually.
LIVING_EVENT_TYPES: tuple[type, ...] = (
    ContextFetchEvent,
    SessionStartEvent,
    SessionCompleteEvent,
    WorktreeSpawnEvent,
    WorktreeArchiveEvent,
    AgentInterventionEvent,
    LivingTaskEvent,
    BranchPushedEvent,
    PrStateChangedEvent,
    MergeCompletedEvent,
    MergeFailedEvent,
)


# Stable mapping from event class -> ``kind`` string written to the
# living_event table. Kept here (next to the dataclasses) so a new event
# type can be added in one place.
LIVING_EVENT_KINDS: dict[type, str] = {
    ContextFetchEvent: "context_fetch",
    SessionStartEvent: "session_start",
    SessionCompleteEvent: "session_complete",
    WorktreeSpawnEvent: "worktree_spawn",
    WorktreeArchiveEvent: "worktree_archive",
    AgentInterventionEvent: "agent_intervention",
    # LivingTaskEvent uses its `kind` field for the kind string;
    # the persistence handler must read it from the instance.
    LivingTaskEvent: "living_task",
    BranchPushedEvent: "branch_pushed",
    PrStateChangedEvent: "pr_state_changed",
    MergeCompletedEvent: "merge_completed",
    MergeFailedEvent: "merge_failed",
}
