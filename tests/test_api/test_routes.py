"""Tests for API routes using FastAPI TestClient with mocked dependencies."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_current_member, get_db, get_org
from src.api.routes import router as api_router
from src.shared.types import RoleType


@pytest.fixture
def mock_db():
    """Create a mock async session."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_member():
    """Create a mock OrgMember for dependency injection."""
    member = MagicMock()
    member.id = uuid.UUID("00000000-0000-0000-0000-000000000060")
    member.org_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    member.person_entity_id = uuid.UUID("00000000-0000-0000-0000-000000000010")
    member.role = RoleType.ENGINEER
    member.email = "alice@test.com"
    member.display_name = "Alice Test"
    return member


@pytest.fixture
def mock_org():
    """Create a mock Organization for dependency injection."""
    org = MagicMock()
    org.id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    org.name = "Test Org"
    org.slug = "test-org"
    org.is_demo = False
    org.created_at = datetime.now(timezone.utc)
    return org


@pytest.fixture
def app(mock_db, mock_member, mock_org):
    """Create a minimal test app with the API router and mocked dependencies."""
    test_app = FastAPI()
    test_app.include_router(api_router)

    async def override_db():
        yield mock_db

    async def override_member(org_id=None, member_email=None, user=None, db=None):
        return mock_member

    async def override_org(org_id=None, db=None):
        return mock_org

    test_app.dependency_overrides[get_db] = override_db
    test_app.dependency_overrides[get_current_member] = override_member
    test_app.dependency_overrides[get_org] = override_org

    return test_app


@pytest.fixture
def client(app):
    """Create a TestClient."""
    return TestClient(app, raise_server_exceptions=False)


def test_list_orgs(client, mock_db):
    """GET /api/orgs should return 200."""
    mock_org_obj = MagicMock()
    mock_org_obj.id = uuid.uuid4()
    mock_org_obj.name = "Demo Org"
    mock_org_obj.slug = "demo"
    mock_org_obj.is_demo = True
    mock_org_obj.created_at = datetime.now(timezone.utc)

    result = MagicMock()
    result.scalars.return_value.all.return_value = [mock_org_obj]
    mock_db.execute.return_value = result

    response = client.get("/api/orgs")
    assert response.status_code == 200


def test_list_orgs_empty(client, mock_db):
    """GET /api/orgs with no orgs should return 200 with empty list."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = result

    response = client.get("/api/orgs")
    assert response.status_code == 200
