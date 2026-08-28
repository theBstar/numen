"""Tests for WS1 PRD-proposal MCP tools + service."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp.tools import (
    get_proposal_status,
    list_proposals_tool,
    propose_prd_update,
)
from src.services.proposals import (
    DEFAULT_EXPIRY_DAYS,
    ProposalErrorCode,
    ProposalServiceError,
    ProposeIn,
    _hash_content,
    approve_proposal,
    expire_stale_proposals,
    get_proposal,
    list_proposals,
    reject_proposal,
)
from src.services.proposals import (
    propose_prd_update as svc_propose,
)
from tests.conftest import TEST_ORG_ID

PROPOSAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000900")


def _wiki(slug: str = "auth-flow", content: str = "# Auth\n\nOriginal."):
    wf = MagicMock()
    wf.org_id = TEST_ORG_ID
    wf.slug = slug
    wf.content = content
    wf.summary = content[:200]
    wf.is_manual = False
    wf.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)
    return wf


def _proposal(**overrides):
    p = MagicMock()
    p.id = overrides.get("id", PROPOSAL_ID)
    p.org_id = overrides.get("org_id", TEST_ORG_ID)
    p.feature_slug = overrides.get("feature_slug", "auth-flow")
    p.section_anchor = overrides.get("section_anchor", "callbacks")
    p.diff_md = overrides.get("diff_md", "# new section content")
    p.rationale = overrides.get("rationale", "")
    p.base_content_hash = overrides.get(
        "base_content_hash", _hash_content("# Auth\n\nOriginal.")
    )
    p.base_updated_at = overrides.get("base_updated_at", datetime.now(timezone.utc))
    p.status = overrides.get("status", "pending")
    p.proposer_user_id = overrides.get("proposer_user_id", None)
    p.decided_by_user_id = overrides.get("decided_by_user_id", None)
    p.decided_at = overrides.get("decided_at", None)
    p.decided_reason = overrides.get("decided_reason", None)
    p.applied_content_hash = overrides.get("applied_content_hash", None)
    p.created_at = overrides.get("created_at", datetime.now(timezone.utc))
    p.expires_at = overrides.get(
        "expires_at",
        datetime.now(timezone.utc) + timedelta(days=DEFAULT_EXPIRY_DAYS),
    )
    return p


def _exec(returns):
    """Build a mock execute() returning a result with scalar_one_or_none()."""
    r = MagicMock()
    r.scalar_one_or_none.return_value = returns
    return r


def _exec_scalars(returns_list):
    r = MagicMock()
    r.scalars.return_value.all.return_value = returns_list
    return r


# ── service: propose ────────────────────────────────────────────────────


async def test_propose_feature_not_found_raises():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(None))
    with pytest.raises(ProposalServiceError) as exc:
        await svc_propose(
            db, TEST_ORG_ID, None,
            ProposeIn(feature_slug="ghost", section_anchor="x", diff_md="..."),
        )
    assert exc.value.code == ProposalErrorCode.FEATURE_NOT_FOUND


async def test_propose_happy_path_returns_proposal():
    wiki = _wiki()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(wiki))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    proposal = await svc_propose(
        db, TEST_ORG_ID, None,
        ProposeIn(
            feature_slug="auth-flow",
            section_anchor="callbacks",
            diff_md="# updated",
            rationale="aligns with new design doc",
        ),
    )
    assert proposal.feature_slug == "auth-flow"
    assert proposal.base_content_hash == _hash_content(wiki.content)
    db.add.assert_called_once()


# ── service: approve hash-stale ─────────────────────────────────────────


async def test_approve_stale_when_content_drifted():
    """The wiki was edited between propose and approve; hash mismatch -> stale."""
    base_content = "# Auth\n\nOriginal."
    new_content = "# Auth\n\nDrifted!"
    proposal = _proposal(base_content_hash=_hash_content(base_content))
    drifted_wiki = _wiki(content=new_content)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_exec(proposal), _exec(drifted_wiki)])
    db.commit = AsyncMock()

    with pytest.raises(ProposalServiceError) as exc:
        await approve_proposal(db, TEST_ORG_ID, proposal.id, uuid.uuid4())
    assert exc.value.code == ProposalErrorCode.STALE
    assert "current_base_hash" in exc.value.extra
    assert proposal.status == "stale"


async def test_approve_happy_path_marks_applied_and_mutates_wiki():
    base_content = "# Auth\n\nOriginal."
    diff_md = "# Auth\n\nReplaced by agent."
    proposal = _proposal(
        base_content_hash=_hash_content(base_content),
        diff_md=diff_md,
    )
    wiki = _wiki(content=base_content)

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[_exec(proposal), _exec(wiki)])
    db.commit = AsyncMock()

    decider = uuid.uuid4()
    out = await approve_proposal(db, TEST_ORG_ID, proposal.id, decider)
    assert out.status == "applied"
    assert out.decided_by_user_id == decider
    assert out.applied_content_hash == _hash_content(diff_md)
    assert wiki.content == diff_md
    assert wiki.is_manual is True


async def test_approve_already_applied_raises_not_pending():
    proposal = _proposal(status="applied")
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(proposal))
    with pytest.raises(ProposalServiceError) as exc:
        await approve_proposal(db, TEST_ORG_ID, proposal.id, uuid.uuid4())
    assert exc.value.code == ProposalErrorCode.NOT_PENDING


# ── service: reject ─────────────────────────────────────────────────────


async def test_reject_marks_status_with_reason():
    proposal = _proposal()
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(proposal))
    db.commit = AsyncMock()
    decider = uuid.uuid4()
    out = await reject_proposal(db, TEST_ORG_ID, proposal.id, decider, reason="not the direction")
    assert out.status == "rejected"
    assert out.decided_by_user_id == decider
    assert out.decided_reason == "not the direction"


# ── service: get + list ─────────────────────────────────────────────────


async def test_get_cross_org_returns_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(None))
    with pytest.raises(ProposalServiceError) as exc:
        await get_proposal(db, TEST_ORG_ID, uuid.uuid4())
    assert exc.value.code == ProposalErrorCode.NOT_FOUND


async def test_list_returns_empty_when_no_proposals():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec_scalars([]))
    out = await list_proposals(db, TEST_ORG_ID)
    assert out == []


async def test_expire_sweep_transitions_pending_past_deadline():
    expired_a = _proposal(
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    expired_b = _proposal(
        id=uuid.uuid4(),
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec_scalars([expired_a, expired_b]))
    db.commit = AsyncMock()
    n = await expire_stale_proposals(db)
    assert n == 2
    assert expired_a.status == "expired"
    assert expired_b.status == "expired"


# ── MCP tool wrappers translate errors ──────────────────────────────────


async def test_mcp_propose_translates_feature_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(None))
    out = json.loads(
        await propose_prd_update(
            db, TEST_ORG_ID, None,
            "ghost", "section", "diff text",
        )
    )
    assert out["error"]["code"] == "wiki_feature_not_found"
    assert out["error"]["suggested_next_tool"] == "list_wiki_features"


async def test_mcp_propose_invalid_expiry_returns_invalid_argument():
    db = AsyncMock()
    out = json.loads(
        await propose_prd_update(
            db, TEST_ORG_ID, None,
            "x", "y", "z", expires_in_days=999,
        )
    )
    assert out["error"]["code"] == "invalid_argument"


async def test_mcp_get_proposal_status_invalid_uuid():
    db = AsyncMock()
    out = json.loads(await get_proposal_status(db, TEST_ORG_ID, "not-a-uuid"))
    assert out["error"]["code"] == "invalid_uuid"


async def test_mcp_get_proposal_status_translates_not_found():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec(None))
    out = json.loads(
        await get_proposal_status(db, TEST_ORG_ID, str(PROPOSAL_ID))
    )
    assert out["error"]["code"] == "proposal_not_found"


async def test_mcp_list_proposals_returns_envelope():
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_exec_scalars([_proposal()]))
    out = json.loads(await list_proposals_tool(db, TEST_ORG_ID))
    assert out["count"] == 1
    assert out["items"][0]["feature_slug"] == "auth-flow"
