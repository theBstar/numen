"""Stable error envelope for Numen MCP tools.

Every MCP tool returns a JSON string. Errors must use this envelope so agents
can branch on `code` (stable across versions) instead of parsing prose. Adding
new fields is allowed (additive); changing existing field semantics is not.

Envelope:
    {
      "error": {
        "code": "task_not_found",
        "message": "No task with id 1f3a... in this org.",
        "hint": "Use search_entities or find_matching_task to discover task IDs.",
        "retryable": false,
        "suggested_next_tool": "search_entities",
        "docs_url": "https://numen.team/docs/errors#task_not_found"
      }
    }

Usage:
    return error_response(
        ErrorCode.TASK_NOT_FOUND,
        message=f"No task with id {task_id} in this org.",
        suggested_next_tool="search_entities",
    )
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any


def _docs_base() -> str:
    """Where error documentation lives for this instance.

    Defaults to the project's own docs. A self-hosted deployment can point
    this at its own runbook so an agent hitting an error is not sent to
    somebody else's website.
    """
    from src.config import settings

    configured = (getattr(settings, "mcp_docs_base_url", "") or "").strip()
    return configured.rstrip("/") or "https://github.com/numen-app/numen/blob/main/docs/errors.md"


class ErrorCode(str, Enum):
    """Stable error codes. Agents may branch on these. Additive only."""

    # Auth & access
    AUTH_REQUIRED = "auth_required"
    ORG_MISMATCH = "org_mismatch"
    USER_BINDING_REQUIRED = "user_binding_required"

    # Org scoping
    ORG_ID_REQUIRED = "org_id_required"

    # Input validation
    INVALID_UUID = "invalid_uuid"
    INVALID_ARGUMENT = "invalid_argument"
    INVALID_ENTITY_TYPE = "invalid_entity_type"
    INVALID_SOURCE = "invalid_source"
    INVALID_STATUS = "invalid_status"
    INVALID_PRIORITY = "invalid_priority"
    INVALID_LEVEL = "invalid_level"

    # Not found
    ENTITY_NOT_FOUND = "entity_not_found"
    TASK_NOT_FOUND = "task_not_found"
    GOAL_NOT_FOUND = "goal_not_found"
    PROJECT_NOT_FOUND = "project_not_found"
    PERSON_NOT_FOUND = "person_not_found"
    BRIEFING_NOT_FOUND = "briefing_not_found"
    WIKI_FEATURE_NOT_FOUND = "wiki_feature_not_found"
    PROPOSAL_NOT_FOUND = "proposal_not_found"

    # Domain rules
    TASK_TRANSITION_REJECTED = "task_transition_rejected"
    PROPOSAL_STALE = "proposal_stale"
    PROPOSAL_DUPLICATE_PENDING = "proposal_duplicate_pending"
    DEDUPE_BLOCKED = "dedupe_blocked"

    # External
    UPSTREAM_RATE_LIMITED = "upstream_rate_limited"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    UPSTREAM_ERROR = "upstream_error"

    # Internal
    INTERNAL_ERROR = "internal_error"


_DEFAULT_RETRYABLE: dict[ErrorCode, bool] = {
    ErrorCode.UPSTREAM_RATE_LIMITED: True,
    ErrorCode.UPSTREAM_TIMEOUT: True,
    ErrorCode.UPSTREAM_ERROR: True,
}


def error_response(
    code: ErrorCode,
    *,
    message: str,
    hint: str | None = None,
    retryable: bool | None = None,
    suggested_next_tool: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    """Build a JSON error envelope. Returns a string ready to return from a tool.

    Args:
        code: Stable error code from ErrorCode.
        message: Human-readable message (may include caller-supplied IDs).
        hint: Optional next-step hint for the agent.
        retryable: Override default retryability for the code.
        suggested_next_tool: Tool the agent should consider calling next.
        extra: Per-code extension fields (e.g. {"current_base_hash": "..."}).
    """
    if retryable is None:
        retryable = _DEFAULT_RETRYABLE.get(code, False)
    body: dict[str, Any] = {
        "code": code.value,
        "message": message,
        "retryable": retryable,
        "docs_url": f"{_docs_base()}#{code.value}",
    }
    if hint is not None:
        body["hint"] = hint
    if suggested_next_tool is not None:
        body["suggested_next_tool"] = suggested_next_tool
    if extra:
        body.update(extra)
    return json.dumps({"error": body})
