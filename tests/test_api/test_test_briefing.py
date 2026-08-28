"""Tests for the POST /api/orgs/{org_id}/briefings/test endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_current_member, get_db
from src.api.routes_briefings import router as briefings_router
from src.shared.models import Briefing
from src.shared.types import BriefingItem, EntityType, RoleType


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_member():
    m = MagicMock()
    m.id = uuid.uuid4()
    m.org_id = uuid.uuid4()
    m.user_id = uuid.uuid4()
    m.role = RoleType.ENGINEER
    m.email = "alice@example.com"
    m.display_name = "Alice"
    m.preferences = {}
    return m


@pytest.fixture
def app(mock_db, mock_member):
    test_app = FastAPI()
    test_app.include_router(briefings_router)

    async def override_db():
        yield mock_db

    async def override_member():
        return mock_member

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_current_member] = override_member
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def _items(n: int = 1) -> list[BriefingItem]:
    return [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title=f"item {i}",
            why_it_matters="because",
            urgency_score=0.5,
        )
        for i in range(n)
    ]


def _added_briefing_rows(mock_db) -> list:
    return [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], Briefing)]


def test_email_channel_delivers(client, mock_db, mock_member):
    mock_member.preferences = {"briefing_channel": "email"}

    org_id = mock_member.org_id

    with (
        patch("src.briefing.assembler.assemble_briefing", new=AsyncMock(return_value=(_items(2), None))),
        patch("src.briefing.delivery.send_briefing_email", new=AsyncMock(return_value=True)),
        patch("src.briefing.templates.render_briefing_email", return_value=("<html/>", "txt")),
        patch("src.llm.actions.generate_briefing_narrative", new=AsyncMock(return_value={"narrative": "hi"})),
    ):
        resp = client.post(f"/api/orgs/{org_id}/briefings/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["channel"] == "email"
    assert body["delivered"] is True
    assert body["fallback_reason"] is None
    assert body["item_count"] == 2
    assert "alice@example.com" in body["message"]
    # Critically: no Briefing row should be persisted.
    assert _added_briefing_rows(mock_db) == []


def test_slack_channel_success(client, mock_db, mock_member):
    mock_member.preferences = {"briefing_channel": "slack"}
    org_id = mock_member.org_id

    with (
        patch("src.briefing.assembler.assemble_briefing", new=AsyncMock(return_value=(_items(3), None))),
        patch("src.briefing.slack_delivery.deliver_via_slack", new=AsyncMock(return_value=(True, None))),
        patch("src.llm.actions.generate_briefing_narrative", new=AsyncMock(return_value={"narrative": "hi"})),
    ):
        resp = client.post(f"/api/orgs/{org_id}/briefings/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["channel"] == "slack"
    assert body["delivered"] is True
    assert body["fallback_reason"] is None
    assert body["item_count"] == 3
    assert "Slack DM" in body["message"]
    assert _added_briefing_rows(mock_db) == []


def test_slack_user_not_found_does_not_fall_back_to_email(client, mock_db, mock_member):
    """Test path must report Slack failure verbatim, NOT silently email."""
    mock_member.preferences = {"briefing_channel": "slack"}
    org_id = mock_member.org_id

    email_mock = AsyncMock(return_value=True)
    with (
        patch("src.briefing.assembler.assemble_briefing", new=AsyncMock(return_value=(_items(1), None))),
        patch("src.briefing.slack_delivery.deliver_via_slack", new=AsyncMock(return_value=(False, "user_not_found"))),
        patch("src.briefing.delivery.send_briefing_email", new=email_mock),
    ):
        resp = client.post(f"/api/orgs/{org_id}/briefings/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["channel"] == "slack"
    assert body["delivered"] is False
    assert body["fallback_reason"] == "user_not_found"
    assert "Slack profile email" in body["message"]
    email_mock.assert_not_awaited()
    assert _added_briefing_rows(mock_db) == []


def test_empty_items_synthesizes_one(client, mock_db, mock_member):
    mock_member.preferences = {"briefing_channel": "email"}
    org_id = mock_member.org_id

    with (
        patch("src.briefing.assembler.assemble_briefing", new=AsyncMock(return_value=([], "no_urgent_signals"))),
        patch("src.briefing.delivery.send_briefing_email", new=AsyncMock(return_value=True)),
        patch("src.briefing.templates.render_briefing_email", return_value=("<html/>", "txt")),
    ):
        resp = client.post(f"/api/orgs/{org_id}/briefings/test")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["item_count"] == 1  # synthetic placeholder item
    assert body["delivered"] is True


def test_slack_missing_scopes_message(client, mock_db, mock_member):
    mock_member.preferences = {"briefing_channel": "slack"}
    org_id = mock_member.org_id

    with (
        patch("src.briefing.assembler.assemble_briefing", new=AsyncMock(return_value=(_items(1), None))),
        patch("src.briefing.slack_delivery.deliver_via_slack", new=AsyncMock(return_value=(False, "missing_scopes"))),
    ):
        resp = client.post(f"/api/orgs/{org_id}/briefings/test")

    body = resp.json()
    assert body["delivered"] is False
    assert body["fallback_reason"] == "missing_scopes"
    assert "reconnect Slack" in body["message"]
