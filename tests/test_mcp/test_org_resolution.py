"""Tests for server-side org_id and agent_id resolution (WS0)."""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from unittest.mock import patch

from src.mcp import server as mcp_server

# We test the helpers directly. They live inside create_mcp_server() in the
# real factory but the module-level versions (_verify_org_access /
# _resolve_org_uuid / _resolve_agent_uuid) are what tools delegate to.


@contextmanager
def _patched_actor(org: str | None, user: str | None = None):
    """Patch the auth context that _resolve_org_uuid reads from."""
    with patch.object(mcp_server, "_get_actor", return_value=(org, user)):
        yield


TEST_ORG = "00000000-0000-0000-0000-000000000001"
OTHER_ORG = "00000000-0000-0000-0000-000000000099"
TEST_USER = "00000000-0000-0000-0000-000000000010"


# ── _resolve_org_uuid ─────────────────────────────────────────────────


def test_resolve_org_uuid_uses_auth_context_when_caller_omits():
    with _patched_actor(TEST_ORG):
        org_uuid, err = mcp_server._resolve_org_uuid(None, require_auth=True)
    assert err is None
    assert org_uuid == uuid.UUID(TEST_ORG)


def test_resolve_org_uuid_auth_context_wins_over_matching_explicit():
    with _patched_actor(TEST_ORG):
        org_uuid, err = mcp_server._resolve_org_uuid(TEST_ORG, require_auth=True)
    assert err is None
    assert org_uuid == uuid.UUID(TEST_ORG)


def test_resolve_org_uuid_rejects_mismatch():
    with _patched_actor(TEST_ORG):
        org_uuid, err = mcp_server._resolve_org_uuid(OTHER_ORG, require_auth=True)
    assert org_uuid is None
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "org_mismatch"


def test_resolve_org_uuid_stdio_with_explicit_org():
    """No auth context, caller supplies org_id - that's the stdio happy path."""
    with _patched_actor(None):
        org_uuid, err = mcp_server._resolve_org_uuid(TEST_ORG, require_auth=False)
    assert err is None
    assert org_uuid == uuid.UUID(TEST_ORG)


def test_resolve_org_uuid_stdio_without_org_errors():
    with _patched_actor(None):
        org_uuid, err = mcp_server._resolve_org_uuid(None, require_auth=False)
    assert org_uuid is None
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "org_id_required"


def test_resolve_org_uuid_no_auth_in_sse_mode_errors():
    """SSE mode (require_auth=True) must reject unauthenticated calls even
    if caller tries to pass an org_id."""
    with _patched_actor(None):
        org_uuid, err = mcp_server._resolve_org_uuid(TEST_ORG, require_auth=True)
    assert org_uuid is None
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "auth_required"


def test_resolve_org_uuid_invalid_uuid_format():
    with _patched_actor(None):
        org_uuid, err = mcp_server._resolve_org_uuid("not-a-uuid", require_auth=False)
    assert org_uuid is None
    body = json.loads(err)
    assert body["error"]["code"] == "invalid_uuid"


# ── _resolve_agent_uuid ───────────────────────────────────────────────


def test_resolve_agent_uuid_uses_explicit_when_provided():
    explicit = "11111111-1111-1111-1111-111111111111"
    with _patched_actor(TEST_ORG, TEST_USER):
        agent_uuid, err = mcp_server._resolve_agent_uuid(explicit)
    assert err is None
    assert agent_uuid == uuid.UUID(explicit)


def test_resolve_agent_uuid_falls_back_to_user_id():
    with _patched_actor(TEST_ORG, TEST_USER):
        agent_uuid, err = mcp_server._resolve_agent_uuid(None)
    assert err is None
    assert agent_uuid == uuid.UUID(TEST_USER)


def test_resolve_agent_uuid_synthetic_when_no_user_no_explicit():
    with _patched_actor(None):
        agent_uuid, err = mcp_server._resolve_agent_uuid(None)
    assert err is None
    assert agent_uuid == uuid.UUID(int=0)


def test_resolve_agent_uuid_invalid_explicit_returns_error():
    with _patched_actor(TEST_ORG, TEST_USER):
        agent_uuid, err = mcp_server._resolve_agent_uuid("not-a-uuid")
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "invalid_uuid"


# ── _verify_org_access (legacy helper) still uses error envelope ──────


def test_legacy_verify_org_access_no_auth_no_require_returns_none():
    with _patched_actor(None):
        out = mcp_server._verify_org_access(TEST_ORG, require_auth=False)
    assert out is None


def test_legacy_verify_org_access_no_auth_with_require_returns_envelope():
    with _patched_actor(None):
        out = mcp_server._verify_org_access(TEST_ORG, require_auth=True)
    assert out is not None
    body = json.loads(out)
    assert body["error"]["code"] == "auth_required"


def test_legacy_verify_org_access_mismatch_returns_envelope():
    with _patched_actor(TEST_ORG):
        out = mcp_server._verify_org_access(OTHER_ORG)
    assert out is not None
    body = json.loads(out)
    assert body["error"]["code"] == "org_mismatch"


# ── _require_write uses error envelope ────────────────────────────────


def test_require_write_no_auth_no_require_passes():
    with _patched_actor(None):
        err, user = mcp_server._require_write(require_auth=False)
    assert err is None
    assert user is None


def test_require_write_no_auth_with_require_returns_envelope():
    with _patched_actor(None):
        err, user = mcp_server._require_write(require_auth=True)
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "auth_required"


def test_require_write_legacy_key_returns_user_binding_required():
    """Auth present but user_id missing = legacy key."""
    with _patched_actor(TEST_ORG, None):
        err, user = mcp_server._require_write(require_auth=True)
    assert err is not None
    body = json.loads(err)
    assert body["error"]["code"] == "user_binding_required"
