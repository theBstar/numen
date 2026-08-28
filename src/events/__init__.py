"""Event bus for graph triggers."""

from src.events.bus import bus
from src.events.handlers import register_all
from src.events.types import (
    AgentInterventionEvent,
    BranchPushedEvent,
    BriefingRequested,
    ContextFetchEvent,
    EdgeCreated,
    EntityUpserted,
    LivingTaskEvent,
    MergeCompletedEvent,
    MergeFailedEvent,
    PrStateChangedEvent,
    SessionCompleteEvent,
    SessionStartEvent,
    SyncCompleted,
    WorktreeArchiveEvent,
    WorktreeSpawnEvent,
)

__all__ = [
    "bus",
    "register_all",
    "EdgeCreated",
    "EntityUpserted",
    "SyncCompleted",
    "BriefingRequested",
    # Living events
    "ContextFetchEvent",
    "LivingTaskEvent",
    "SessionStartEvent",
    "SessionCompleteEvent",
    "WorktreeSpawnEvent",
    "WorktreeArchiveEvent",
    "AgentInterventionEvent",
    "BranchPushedEvent",
    "PrStateChangedEvent",
    "MergeCompletedEvent",
    "MergeFailedEvent",
]
