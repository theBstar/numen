"""Regression: X-Member-Email must not bypass JWT when allow_header_auth is False."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db, get_org
from src.api.routes import router as api_router
from src.config import settings


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(api_router)

    async def override_db():
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=None)
        db.execute = AsyncMock(return_value=result)
        yield db

    async def override_org(org_id=None, db=None):
        org = MagicMock()
        org.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        return org

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_org] = override_org
    # IMPORTANT: do NOT override get_current_member; we are testing the real one.
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_header_auth_rejected_when_flag_off(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_header_auth", False)
    org_id = "00000000-0000-0000-0000-000000000001"
    resp = client.get(
        f"/api/orgs/{org_id}/urgency",
        headers={"X-Member-Email": "attacker@example.com"},
    )
    assert resp.status_code == 401


def test_header_auth_allowed_when_flag_on(client, monkeypatch):
    """Dev-mode path still works so local dev / demo seeder don't break."""
    monkeypatch.setattr(settings, "allow_header_auth", True)
    org_id = "00000000-0000-0000-0000-000000000001"
    # With no member row matching, we expect 403 (not 401) — i.e. the header
    # was accepted but the lookup failed. That proves the dev path is live.
    resp = client.get(
        f"/api/orgs/{org_id}/urgency",
        headers={"X-Member-Email": "nobody@example.com"},
    )
    assert resp.status_code in (403, 404)


def test_no_auth_returns_401(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_header_auth", True)
    org_id = "00000000-0000-0000-0000-000000000001"
    resp = client.get(f"/api/orgs/{org_id}/urgency")
    assert resp.status_code == 401
