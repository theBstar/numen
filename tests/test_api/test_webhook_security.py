"""Webhook signature verification end-to-end tests."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.routes_connectors import router as connectors_router
from src.config import settings
from src.shared.webhook_secrets import github_webhook_secret


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(connectors_router)

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: [])))
        db.commit = AsyncMock()
        yield db

    test_app.dependency_overrides[get_db] = override_db
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _webhook_secrets(monkeypatch):
    """Ensure signing secrets are set so the verifier runs the real path."""
    monkeypatch.setattr(settings, "webhook_required", True)
    monkeypatch.setattr(settings, "slack_signing_secret", "test-slack-secret")
    monkeypatch.setattr(settings, "github_client_secret", "test-github-secret")
    monkeypatch.setattr(settings, "linear_signing_secret", "test-linear-secret")


def _sign_github(body: bytes) -> str:
    return "sha256=" + hmac.new(b"test-github-secret", body, hashlib.sha256).hexdigest()


def _sign_linear(body: bytes) -> str:
    return hmac.new(b"test-linear-secret", body, hashlib.sha256).hexdigest()


def _sign_slack(body: bytes, timestamp: str) -> str:
    base = f"v0:{timestamp}:{body.decode()}"
    return "v0=" + hmac.new(b"test-slack-secret", base.encode(), hashlib.sha256).hexdigest()


def test_github_webhook_rejects_missing_signature(client):
    resp = client.post("/api/webhooks/github", json={"repository": {"full_name": "x/y"}})
    assert resp.status_code == 401


def test_github_webhook_rejects_bad_signature(client):
    body = b'{"repository": {"full_name": "x/y"}}'
    resp = client.post(
        "/api/webhooks/github",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


def test_github_webhook_accepts_valid_signature(client):
    payload = {"repository": {"full_name": "x/y"}}
    body = json.dumps(payload).encode()
    resp = client.post(
        "/api/webhooks/github",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign_github(body)},
    )
    # With no tokens in DB the route returns {"status": "ignored"} but must not 401.
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_linear_webhook_rejects_missing_signature(client):
    resp = client.post("/api/webhooks/linear", json={"organizationId": "abc"})
    assert resp.status_code == 401


def test_linear_webhook_rejects_bad_signature(client):
    body = b'{"organizationId": "abc"}'
    resp = client.post(
        "/api/webhooks/linear",
        content=body,
        headers={"Content-Type": "application/json", "Linear-Signature": "deadbeef"},
    )
    assert resp.status_code == 401


def test_linear_webhook_accepts_valid_signature(client):
    body = b'{"organizationId": "abc"}'
    resp = client.post(
        "/api/webhooks/linear",
        content=body,
        headers={"Content-Type": "application/json", "Linear-Signature": _sign_linear(body)},
    )
    assert resp.status_code == 200


def test_slack_webhook_rejects_missing_signature(client):
    resp = client.post("/api/webhooks/slack", json={"team_id": "T1"})
    assert resp.status_code == 401


def test_slack_webhook_rejects_bad_signature(client):
    body = b'{"team_id": "T1"}'
    resp = client.post(
        "/api/webhooks/slack",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": "1234567890",
            "X-Slack-Signature": "v0=deadbeef",
        },
    )
    assert resp.status_code == 401


def test_slack_webhook_accepts_valid_signature(client):
    body = b'{"team_id": "T1"}'
    ts = "1234567890"
    resp = client.post(
        "/api/webhooks/slack",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": ts,
            "X-Slack-Signature": _sign_slack(body, ts),
        },
    )
    assert resp.status_code == 200


def test_missing_secret_fails_closed_in_prod_mode(client, monkeypatch):
    """When webhook_required is True and the secret is empty, we return 503.

    Uses Linear: it has no fallback key, so an unset secret really is unset.
    """
    monkeypatch.setattr(settings, "linear_signing_secret", "")
    resp = client.post(
        "/api/webhooks/linear",
        json={"action": "create"},
    )
    assert resp.status_code == 503


def test_github_still_verifies_without_an_oauth_app(client, monkeypatch):
    """GitHub falls back to SECRET_KEY, so it verifies rather than failing closed.

    Registration resolves the key the same way, so a PAT-only deployment signs
    and checks with the same value. The failure mode here must be 401 on a bad
    signature - never 503 (no key) and never 200 (unverified).
    """
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    monkeypatch.setattr(settings, "github_client_secret", "")
    resp = client.post(
        "/api/webhooks/github",
        json={"repository": {"full_name": "x/y"}},
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert resp.status_code == 401


def test_github_accepts_a_signature_made_with_the_fallback_key(client, monkeypatch):
    """The regression this guards: sign as registration does, verify as intake does."""
    monkeypatch.setattr(settings, "github_webhook_secret", "")
    monkeypatch.setattr(settings, "github_client_secret", "")

    body = b'{"repository": {"full_name": "x/y"}}'
    signing_key = github_webhook_secret(settings)
    signature = "sha256=" + hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()

    resp = client.post(
        "/api/webhooks/github",
        content=body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": signature},
    )
    assert resp.status_code != 401
