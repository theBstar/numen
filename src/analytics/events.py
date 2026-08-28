"""Event catalog + typed helpers.

Every helper swallows its own errors so analytics never breaks a request path.
Call sites stay short: `await track_task_created(member_id, org_id, task_id, ...)`.
"""

from __future__ import annotations

import logging
from typing import Any

from src.analytics.registry import get_tracker
from src.config import settings

logger = logging.getLogger(__name__)


class Events:
    # Auth
    AUTH_LOGGED_IN = "auth.logged_in"
    AUTH_LOGGED_OUT = "auth.logged_out"

    # Briefings
    BRIEFING_GENERATED = "briefing.generated"
    BRIEFING_EMAIL_SENT = "briefing.email_sent"

    # Tasks
    TASK_CREATED = "task.created"
    TASK_STATUS_CHANGED = "task.status_changed"

    # Connectors
    CONNECTOR_CONNECTED = "connector.connected"
    CONNECTOR_DISCONNECTED = "connector.disconnected"
    CONNECTOR_SYNC_COMPLETED = "connector.sync_completed"
    CONNECTOR_SYNC_FAILED = "connector.sync_failed"

    # Chat
    CHAT_TOOL_INVOKED = "chat.tool_invoked"
    CHAT_RESPONSE_COMPLETED = "chat.response_completed"

    # Workers / reliability
    WORKER_JOB_FAILED = "worker.job_failed"


def _reserved(org_id: str | None, source: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {
        "source": source,
        "environment": settings.environment,
    }
    if org_id:
        props["org_id"] = org_id
    if extra:
        props.update({k: v for k, v in extra.items() if v is not None})
    return props


async def _safe_track(event: str, distinct_id: str, properties: dict[str, Any]) -> None:
    if not distinct_id:
        return
    try:
        await get_tracker().track(event, distinct_id, properties)
    except Exception as e:
        logger.warning("analytics track failed event=%s: %s", event, e)


async def track_task_created(
    *,
    member_id: str,
    org_id: str,
    task_id: str,
    source: str = "api",
    origin: str | None = None,
    project_id: str | None = None,
    goal_id: str | None = None,
) -> None:
    await _safe_track(
        Events.TASK_CREATED,
        member_id,
        _reserved(org_id, source, {"task_id": task_id, "origin": origin, "project_id": project_id, "goal_id": goal_id}),
    )


async def track_task_status_changed(
    *,
    member_id: str,
    org_id: str,
    task_id: str,
    from_status: str,
    to_status: str,
    source: str = "api",
) -> None:
    await _safe_track(
        Events.TASK_STATUS_CHANGED,
        member_id,
        _reserved(org_id, source, {"task_id": task_id, "from_status": from_status, "to_status": to_status}),
    )


async def track_briefing_generated(
    *,
    member_id: str,
    org_id: str,
    briefing_id: str,
    item_count: int,
    generation_ms: int,
    trigger: str,
    source: str = "worker",
) -> None:
    await _safe_track(
        Events.BRIEFING_GENERATED,
        member_id,
        _reserved(
            org_id,
            source,
            {
                "briefing_id": briefing_id,
                "item_count": item_count,
                "generation_ms": generation_ms,
                "trigger": trigger,
            },
        ),
    )


async def track_connector_connected(
    *,
    member_id: str,
    org_id: str,
    connector: str,
    scopes: list[str] | None = None,
    source: str = "api",
) -> None:
    await _safe_track(
        Events.CONNECTOR_CONNECTED,
        member_id,
        _reserved(org_id, source, {"connector": connector, "scopes": scopes or []}),
    )


async def track_connector_sync_completed(
    *,
    org_id: str,
    connector: str,
    entities_upserted: int,
    duration_ms: int,
    member_id: str = "system",
    source: str = "worker",
) -> None:
    await _safe_track(
        Events.CONNECTOR_SYNC_COMPLETED,
        member_id,
        _reserved(
            org_id,
            source,
            {"connector": connector, "entities_upserted": entities_upserted, "duration_ms": duration_ms},
        ),
    )


async def track_worker_job_failed(
    *,
    job: str,
    error: str,
    org_id: str | None = None,
    member_id: str = "system",
    attempt: int = 1,
    source: str = "worker",
) -> None:
    await _safe_track(
        Events.WORKER_JOB_FAILED,
        member_id,
        _reserved(org_id, source, {"job": job, "error": error[:500], "attempt": attempt}),
    )
