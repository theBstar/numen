"""Tests for Slack DM briefing delivery."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.briefing.slack_delivery import deliver_via_slack
from src.shared.types import BriefingItem, EntityType, SourceType


def _make_member(email: str = "alice@example.com"):
    member = MagicMock()
    member.id = uuid.uuid4()
    member.org_id = uuid.uuid4()
    member.email = email
    member.display_name = "Alice"
    return member


def _make_token(scopes: str = "chat:write,im:write,users:read.email,users:read"):
    token = MagicMock()
    token.access_token = "xoxb-test"
    token.scopes = scopes
    token.connector = SourceType.SLACK
    return token


def _make_db_returning(token):
    db = AsyncMock()
    scalar_result = MagicMock()
    scalar_result.scalar_one_or_none = MagicMock(return_value=token)
    db.execute = AsyncMock(return_value=scalar_result)
    return db


def _items() -> list[BriefingItem]:
    return [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="Ship feature",
            why_it_matters="Blocking launch",
            urgency_score=0.9,
        )
    ]


@pytest.mark.asyncio
async def test_deliver_returns_no_token_when_missing():
    db = _make_db_returning(None)
    member = _make_member()
    ok, reason = await deliver_via_slack(db, member, _items())
    assert not ok
    assert reason == "no_token"


@pytest.mark.asyncio
async def test_deliver_returns_missing_scopes_for_legacy_token():
    # Legacy token has no chat:write -- predates the bot scope split.
    db = _make_db_returning(_make_token(scopes="channels:history,users:read"))
    member = _make_member()
    ok, reason = await deliver_via_slack(db, member, _items())
    assert not ok
    assert reason == "missing_scopes"


class _MockResp:
    def __init__(self, json_body: dict, status_code: int = 200):
        self._body = json_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=MagicMock(), response=MagicMock())

    def json(self):
        return self._body


def _patch_client(*, get_responses: list[_MockResp], post_responses: list[_MockResp]):
    """Return an AsyncClient mock that yields the queued GET/POST responses in order."""
    get_iter = iter(get_responses)
    post_iter = iter(post_responses)
    client = AsyncMock()
    client.get = AsyncMock(side_effect=lambda *a, **kw: next(get_iter))
    client.post = AsyncMock(side_effect=lambda *a, **kw: next(post_iter))
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = None
    return cm


@pytest.mark.asyncio
async def test_deliver_user_not_found_falls_back():
    db = _make_db_returning(_make_token())
    member = _make_member(email="ghost@example.com")
    cm = _patch_client(
        get_responses=[_MockResp({"ok": False, "error": "users_not_found"})],
        post_responses=[],
    )
    with patch("src.briefing.slack_delivery.httpx.AsyncClient", return_value=cm):
        ok, reason = await deliver_via_slack(db, member, _items())
    assert not ok
    assert reason == "user_not_found"


@pytest.mark.asyncio
async def test_deliver_happy_path_posts_message():
    db = _make_db_returning(_make_token())
    member = _make_member()
    cm = _patch_client(
        get_responses=[_MockResp({"ok": True, "user": {"id": "U123"}})],  # users.lookupByEmail
        post_responses=[
            _MockResp({"ok": True, "channel": {"id": "D456"}}),  # conversations.open
            _MockResp({"ok": True, "ts": "1700000000.000100"}),  # chat.postMessage
        ],
    )
    with patch("src.briefing.slack_delivery.httpx.AsyncClient", return_value=cm):
        ok, reason = await deliver_via_slack(db, member, _items(), narrative="Hello")
    assert ok
    assert reason is None


@pytest.mark.asyncio
async def test_deliver_post_failure_returns_post_failed():
    db = _make_db_returning(_make_token())
    member = _make_member()
    cm = _patch_client(
        get_responses=[_MockResp({"ok": True, "user": {"id": "U123"}})],
        post_responses=[
            _MockResp({"ok": True, "channel": {"id": "D456"}}),
            # invalid_auth is non-retryable, so we get post_failed immediately
            _MockResp({"ok": False, "error": "invalid_auth"}),
        ],
    )
    with patch("src.briefing.slack_delivery.httpx.AsyncClient", return_value=cm):
        ok, reason = await deliver_via_slack(db, member, _items())
    assert not ok
    assert reason == "post_failed"
