"""MCP tool-call observability (WS5).

Two surfaces:
  * `track(...)` async context manager - times the call, classifies the
    return as ok/error (parses error envelope), writes a tiny row to
    mcp_call_log, and emits a structured stdout log line. NO raw args
    persisted (PII risk on diff_md, task_query, etc.).
  * `_redact_args(tool_name, args)` - returns a serializable dict with
    only the safe keys per tool, plus byte-size of the truncated payload.

The aggregator worker (src/workers/mcp_usage_aggregator.py) rolls
mcp_call_log into mcp_usage_daily hourly; the admin endpoint reads from
mcp_usage_daily for cheap dashboard queries.
"""

from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.shared.models import MCPCallLog

logger = logging.getLogger("numen.mcp")


# Per-tool allowlist of arg keys that are SAFE to log as part of args_size.
# Sensitive fields (diff_md, task_query, prompt, raw text content) are NEVER
# in this list. Currently we only persist the BYTE SIZE of the payload, not
# the values - this allowlist is for stdout structured logs only.
_SAFE_LOG_KEYS = {
    "hello_numen": set(),  # no args
    "search_entities": {"entity_type", "limit"},
    "list_tasks": {"status", "priority", "project_id", "limit"},
    "get_context": {"max_tokens"},  # task_query is sensitive
    "find_matching_task": {"limit", "recommend_threshold"},  # description sensitive
    "create_task": {"priority"},  # title/description sensitive
    "update_task_status": {"status"},
    "update_pr_state": {"action", "provider", "draft", "pr_state"},
    "get_pr_state": set(),
    "list_wiki_features": {"status"},
    "append_wiki_note": set(),  # note_markdown sensitive
}


def _redact_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Return a dict of allowlisted args + byte-size of the full args."""
    allowed = _SAFE_LOG_KEYS.get(tool_name, set())
    safe = {k: v for k, v in args.items() if k in allowed and v is not None}
    try:
        size = len(json.dumps(args, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        size = 0
    return {"safe": safe, "args_size_bytes": size}


def _classify_result(result_str: str) -> tuple[str, str | None]:
    """Returns (status, error_code). status is 'ok' or 'error'."""
    try:
        parsed = json.loads(result_str)
    except (TypeError, ValueError):
        return "ok", None
    if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
        return "error", parsed["error"].get("code")
    return "ok", None


@asynccontextmanager
async def track(
    *,
    tool_name: str,
    org_id: UUID | None,
    user_id: UUID | None,
    args: dict[str, Any],
    session_factory: async_sessionmaker[AsyncSession] | None,
):
    """Async context manager that observes a tool call.

    Usage:
        async with observability.track(
            tool_name="get_context",
            org_id=org_uuid,
            user_id=user_uuid,
            args={"task": task, "max_tokens": max_tokens},
            session_factory=_get_session_factory(ctx),
        ) as obs:
            obs.set_result(result_json_string)
        return result
    """
    started = time.monotonic()
    redacted = _redact_args(tool_name, args)

    class _Observer:
        result_str: str | None = None

        def set_result(self, s: str) -> None:
            self.result_str = s

    obs = _Observer()
    raised = False
    try:
        yield obs
    except Exception:
        raised = True
        raise
    finally:
        latency_ms = int((time.monotonic() - started) * 1000)
        if raised:
            status, error_code = "error", "internal_error"
        elif obs.result_str is not None:
            status, error_code = _classify_result(obs.result_str)
        else:
            status, error_code = "ok", None

        # Stdout structured log (always - cheap, no DB hit if everything else fails)
        logger.info(
            json.dumps(
                {
                    "event": "mcp_call",
                    "tool": tool_name,
                    "org_id": str(org_id) if org_id else None,
                    "latency_ms": latency_ms,
                    "status": status,
                    "error_code": error_code,
                    "args_size_bytes": redacted["args_size_bytes"],
                    "safe_args": redacted["safe"],
                }
            )
        )

        # Persist row (best-effort - never raises into the caller)
        if session_factory is not None and org_id is not None:
            try:
                async with session_factory() as db:
                    db.add(
                        MCPCallLog(
                            org_id=org_id,
                            user_id=user_id,
                            tool_name=tool_name,
                            latency_ms=latency_ms,
                            status=status,
                            error_code=error_code,
                            args_size_bytes=redacted["args_size_bytes"],
                        )
                    )
                    await db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "mcp_call_log write failed for tool=%s: %s", tool_name, e
                )
