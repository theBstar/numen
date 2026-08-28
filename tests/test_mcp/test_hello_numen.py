"""Tests for the hello_numen first-call WOW tool."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.mcp.tools import hello_numen
from tests.conftest import TEST_ORG_ID


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.id = TEST_ORG_ID
    org.name = "Test Org"
    org.slug = "test-org"
    return org


def _scalar_db(*scalar_returns):
    """Build a mock_db whose .execute().scalar() / .scalar_one_or_none()
    returns the provided values in order."""
    db = AsyncMock()
    results = []
    for ret in scalar_returns:
        r = MagicMock()
        r.scalar = MagicMock(return_value=ret)
        r.scalar_one_or_none = MagicMock(return_value=ret)
        results.append(r)
    db.execute = AsyncMock(side_effect=results)
    return db


async def test_hello_numen_returns_org_info_when_no_user(mock_org):
    db = _scalar_db(7, 142)  # member_count=7, entity_count=142
    db.get = AsyncMock(return_value=mock_org)

    out = json.loads(await hello_numen(db, TEST_ORG_ID, user_id=None))

    assert out["org"]["name"] == "Test Org"
    assert out["org"]["slug"] == "test-org"
    assert out["org"]["id"] == str(TEST_ORG_ID)
    assert out["member_count"] == 7
    assert out["entity_count"] == 142
    assert out["user_bound"] is False
    assert out["briefing_excerpt"] is None
    assert "available_tools" in out
    assert "task_lifecycle" in out["available_tools"]
    assert "find_matching_task" in out["available_tools"]["task_lifecycle"]
    assert out["sample_first_call"]["tool"] == "get_context"
    assert isinstance(out["next_steps"], list)
    assert len(out["next_steps"]) >= 2


async def test_hello_numen_includes_briefing_excerpt_when_user_bound(mock_org):
    user_id = uuid.uuid4()
    briefing = MagicMock()
    briefing.content = {"summary": "Three PRs in review; ship target by Friday."}

    db = _scalar_db(3, 50, briefing)  # member_count, entity_count, briefing
    db.get = AsyncMock(return_value=mock_org)

    out = json.loads(await hello_numen(db, TEST_ORG_ID, user_id=user_id))

    assert out["user_bound"] is True
    assert out["briefing_excerpt"] == "Three PRs in review; ship target by Friday."


async def test_hello_numen_truncates_long_briefing_excerpt(mock_org):
    user_id = uuid.uuid4()
    long_text = "x" * 500
    briefing = MagicMock()
    briefing.content = {"summary": long_text}

    db = _scalar_db(3, 50, briefing)
    db.get = AsyncMock(return_value=mock_org)

    out = json.loads(await hello_numen(db, TEST_ORG_ID, user_id=user_id))
    assert out["briefing_excerpt"] is not None
    assert len(out["briefing_excerpt"]) == 280


async def test_hello_numen_handles_briefing_with_other_keys(mock_org):
    """Some briefings store under tldr/headline instead of summary."""
    user_id = uuid.uuid4()
    briefing = MagicMock()
    briefing.content = {"headline": "Ship blocker resolved."}

    db = _scalar_db(3, 50, briefing)
    db.get = AsyncMock(return_value=mock_org)

    out = json.loads(await hello_numen(db, TEST_ORG_ID, user_id=user_id))
    assert out["briefing_excerpt"] == "Ship blocker resolved."


async def test_hello_numen_org_not_found_returns_envelope():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)

    out = json.loads(await hello_numen(db, TEST_ORG_ID, user_id=None))
    assert "error" in out
    assert out["error"]["code"] == "auth_required"
