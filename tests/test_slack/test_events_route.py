"""Tests for the Slack events endpoint."""

import hashlib
import hmac
import json
import time
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import routes_slack

SECRET = "test-signing-secret"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes_slack.router)
    with patch.object(routes_slack.settings, "slack_signing_secret", SECRET):
        yield TestClient(app)


def _signed(body: dict, *, timestamp: int | None = None, secret: str = SECRET):
    raw = json.dumps(body)
    ts = str(timestamp if timestamp is not None else int(time.time()))
    signature = (
        "v0=" + hmac.new(secret.encode(), f"v0:{ts}:{raw}".encode(), hashlib.sha256).hexdigest()
    )
    return raw, {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": signature,
        "Content-Type": "application/json",
    }


def test_url_verification_echoes_the_challenge(client):
    raw, headers = _signed({"type": "url_verification", "challenge": "abc123"})
    response = client.post("/api/slack/events", content=raw, headers=headers)
    assert response.status_code == 200
    assert response.json()["challenge"] == "abc123"


def test_unsigned_request_is_rejected(client):
    response = client.post("/api/slack/events", json={"type": "url_verification", "challenge": "x"})
    assert response.status_code == 401


def test_bad_signature_is_rejected(client):
    raw, headers = _signed({"type": "url_verification", "challenge": "x"}, secret="wrong-secret")
    assert client.post("/api/slack/events", content=raw, headers=headers).status_code == 401


def test_replayed_request_is_rejected(client):
    """An old timestamp means a captured request being sent again."""
    raw, headers = _signed({"type": "url_verification", "challenge": "x"}, timestamp=int(time.time()) - 3600)
    assert client.post("/api/slack/events", content=raw, headers=headers).status_code == 401


def test_event_is_queued_for_processing(client):
    body = {
        "type": "event_callback",
        "team_id": "T123",
        "event": {"type": "app_mention", "user": "U1", "text": "<@U0> hi", "ts": "1.1", "channel": "C1"},
    }
    raw, headers = _signed(body)

    with patch("src.api.routes_slack._process") as mock_process:
        response = client.post("/api/slack/events", content=raw, headers=headers)

    assert response.status_code == 200
    mock_process.assert_called_once()
    assert mock_process.call_args[0][0] == "T123"


def test_retries_are_dropped(client):
    """A retry means our ack was slow, not that the user asked twice."""
    body = {"type": "event_callback", "team_id": "T123", "event": {"type": "app_mention"}}
    raw, headers = _signed(body)
    headers["X-Slack-Retry-Num"] = "1"

    with patch("src.api.routes_slack._process") as mock_process:
        response = client.post("/api/slack/events", content=raw, headers=headers)

    assert response.status_code == 200
    mock_process.assert_not_called()


def _signed_form(payload: dict, secret: str = SECRET):
    """Slack posts interactions form-encoded with a JSON payload field."""
    from urllib.parse import quote

    raw = f"payload={quote(json.dumps(payload))}"
    ts = str(int(time.time()))
    signature = "v0=" + hmac.new(secret.encode(), f"v0:{ts}:{raw}".encode(), hashlib.sha256).hexdigest()
    return raw, {
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": signature,
        "Content-Type": "application/x-www-form-urlencoded",
    }


def test_button_press_is_queued(client):
    payload = {
        "type": "block_actions",
        "team": {"id": "T123"},
        "user": {"id": "U1"},
        "channel": {"id": "D1"},
        "actions": [{"action_id": "numen_snooze", "value": "entity:abc"}],
    }
    raw, headers = _signed_form(payload)

    with patch("src.api.routes_slack._process_action") as mock_action:
        response = client.post("/api/slack/interactions", content=raw, headers=headers)

    assert response.status_code == 200
    mock_action.assert_called_once()
    assert mock_action.call_args[0][0] == "T123"


def test_unsigned_interaction_is_rejected(client):
    response = client.post(
        "/api/slack/interactions",
        content="payload=%7B%7D",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 401
