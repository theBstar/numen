"""Tests for the stable MCP error envelope."""

from __future__ import annotations

import json

from src.mcp.errors import ErrorCode, error_response


def test_error_response_has_stable_shape():
    out = json.loads(
        error_response(ErrorCode.TASK_NOT_FOUND, message="Task abc not found.")
    )
    assert "error" in out
    err = out["error"]
    assert err["code"] == "task_not_found"
    assert err["message"] == "Task abc not found."
    assert err["retryable"] is False
    assert err["docs_url"].endswith("#task_not_found")


def test_error_response_includes_optional_fields():
    out = json.loads(
        error_response(
            ErrorCode.PROPOSAL_STALE,
            message="The proposal targets stale content.",
            hint="Re-call propose_prd_update with a fresh diff.",
            suggested_next_tool="get_wiki_feature",
            extra={"current_base_hash": "deadbeef"},
        )
    )
    err = out["error"]
    assert err["hint"] == "Re-call propose_prd_update with a fresh diff."
    assert err["suggested_next_tool"] == "get_wiki_feature"
    assert err["current_base_hash"] == "deadbeef"


def test_upstream_errors_are_retryable_by_default():
    out = json.loads(
        error_response(ErrorCode.UPSTREAM_RATE_LIMITED, message="429 from Notion.")
    )
    assert out["error"]["retryable"] is True


def test_retryable_can_be_overridden():
    out = json.loads(
        error_response(
            ErrorCode.UPSTREAM_TIMEOUT,
            message="connector hung",
            retryable=False,
        )
    )
    assert out["error"]["retryable"] is False


def test_all_error_codes_are_lowercase_snake():
    """Codes are part of the stable contract; reject typos."""
    for code in ErrorCode:
        assert code.value == code.value.lower()
        assert " " not in code.value
        assert "-" not in code.value


def test_docs_url_is_configurable_for_self_hosters():
    """A self-hosted instance should not send agents to someone else's site."""
    import json
    from unittest.mock import patch

    from src.mcp.errors import ErrorCode, error_response

    with patch("src.config.settings.mcp_docs_base_url", "https://wiki.internal/numen/errors"):
        err = json.loads(error_response(ErrorCode.TASK_NOT_FOUND, message="nope"))["error"]

    assert err["docs_url"] == "https://wiki.internal/numen/errors#task_not_found"
