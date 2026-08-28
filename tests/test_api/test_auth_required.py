"""Regression: every org-scoped route must require auth.

Before this test suite, ~57 handlers under /api/orgs/{id}/* leaked data to
unauthenticated callers (e.g. GET /api/orgs/{id}/members returned the full
member list). These tests probe representative endpoints across every router
and assert the unauthenticated response is 401, not 200 or 500.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db, get_org
from src.api.routes import router as core_router
from src.api.routes_api_keys import router as api_keys_router
from src.api.routes_attachments import attachment_router
from src.api.routes_attachments import task_router as attachments_task_router
from src.api.routes_briefings import router as briefings_router
from src.api.routes_connectors import router as connectors_router
from src.api.routes_dispatch import router as dispatch_router
from src.api.routes_edges import router as edges_router
from src.api.routes_goals import router as goals_router
from src.api.routes_kanban import router as kanban_router
from src.api.routes_notifications import router as notifications_router
from src.api.routes_projects import router as projects_router
from src.api.routes_saved_views import router as saved_views_router
from src.api.routes_sprints import router as sprints_router
from src.api.routes_suggestions import router as suggestions_router
from src.api.routes_task_activity import router as task_activity_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_templates import router as templates_router
from src.config import settings

ORG_ID = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def app():
    """Build the full app with every router mounted; override only get_db + get_org.

    Deliberately do NOT override get_current_member — we are testing that the
    real auth dependency rejects unauthenticated requests at every router.
    """
    test_app = FastAPI()
    for r in (
        core_router,
        api_keys_router,
        attachments_task_router,
        attachment_router,
        briefings_router,
        connectors_router,
        dispatch_router,
        edges_router,
        goals_router,
        kanban_router,
        notifications_router,
        projects_router,
        saved_views_router,
        sprints_router,
        suggestions_router,
        task_activity_router,
        tasks_router,
        templates_router,
    ):
        test_app.include_router(r)

    async def override_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db.execute = AsyncMock(return_value=result)
        yield db

    async def override_org(org_id=None, db=None):
        org = MagicMock()
        org.id = uuid.UUID(ORG_ID)
        return org

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_org] = override_org
    return test_app


@pytest.fixture
def client(app, monkeypatch):
    # Force prod-mode auth: X-Member-Email must be refused.
    monkeypatch.setattr(settings, "allow_header_auth", False)
    return TestClient(app, raise_server_exceptions=False)


# Representative endpoint per previously-leaking router. If any of these
# returns < 400 unauthenticated, the router's auth dep is missing.
UNAUTH_ENDPOINTS = [
    # routes.py — previously 500 (the concrete bug we just fixed)
    ("GET", f"/api/orgs/{ORG_ID}"),
    ("GET", f"/api/orgs/{ORG_ID}/members"),
    ("POST", f"/api/orgs/{ORG_ID}/members"),
    ("GET", f"/api/orgs/{ORG_ID}/people/graph"),
    ("GET", f"/api/orgs/{ORG_ID}/entities"),
    ("GET", f"/api/orgs/{ORG_ID}/graph"),
    ("GET", f"/api/orgs/{ORG_ID}/goals"),
    ("POST", f"/api/orgs/{ORG_ID}/goals"),
    ("GET", f"/api/orgs/{ORG_ID}/projects"),
    ("GET", f"/api/orgs/{ORG_ID}/tasks"),
    ("POST", f"/api/orgs/{ORG_ID}/tasks"),
    ("GET", f"/api/orgs/{ORG_ID}/connectors"),
    ("POST", f"/api/orgs/{ORG_ID}/dispatch"),
    ("GET", f"/api/orgs/{ORG_ID}/suggestions"),
    ("GET", f"/api/orgs/{ORG_ID}/activity"),
    # Per-router prefix routers
    ("GET", f"/api/orgs/{ORG_ID}/notifications"),
    ("GET", f"/api/orgs/{ORG_ID}/notifications/unread-count"),
    ("GET", f"/api/orgs/{ORG_ID}/views"),
    ("GET", f"/api/orgs/{ORG_ID}/kanban/settings"),
    ("GET", f"/api/orgs/{ORG_ID}/sprints"),
    ("GET", f"/api/orgs/{ORG_ID}/templates"),
    ("GET", f"/api/orgs/{ORG_ID}/api-keys"),
]


@pytest.mark.parametrize("method,path", UNAUTH_ENDPOINTS)
def test_unauth_request_rejected(client, method, path):
    """Every org-scoped endpoint must 401 when called without a JWT."""
    resp = client.request(method, path, json={})
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code} unauth (body: {resp.text[:200]})"
    )


def test_webhook_not_broken_by_auth_changes(client):
    """POST /api/webhooks/github is intentionally unauth (HMAC-verified).

    It should NOT return 401 from get_current_member (which isn't applied
    there). A bad/missing signature yields 401 from verify_webhook_signature,
    which is correct — but via a different code path.
    """
    resp = client.post("/api/webhooks/github", json={"zen": "hi"}, headers={})
    # Accept either the signature-verification 401 or connector-routing 404,
    # but never 200 (which would mean the handler ran unauth).
    assert resp.status_code in (401, 403, 404), (
        f"webhook returned {resp.status_code} (body: {resp.text[:200]})"
    )
