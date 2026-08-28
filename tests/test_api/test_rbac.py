"""Phase 2: role-based access control on sensitive mutations."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_current_member, get_current_user, get_db, get_org
from src.api.rbac import ADMIN_ROLES, GOALS_ROLES
from src.api.routes import router as core_router
from src.api.routes_goals import router as goals_router
from src.api.routes_projects import router as projects_router
from src.shared.models import OrgMember, User
from src.shared.types import RoleType

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_member(role: RoleType, user_id: uuid.UUID | None = None) -> OrgMember:
    m = MagicMock(spec=OrgMember)
    m.id = uuid.uuid4()
    m.org_id = ORG_ID
    m.email = "member@example.com"
    m.role = role
    m.user_id = user_id
    m.person_entity_id = None
    return m


def _make_user(email: str) -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.email = email
    u.is_active = True
    return u


@pytest.fixture
def app_with_member():
    """Factory that lets each test inject a specific member + user."""

    def _build(member_role: RoleType, user_email: str | None = "normal@example.com"):
        app = FastAPI()
        app.include_router(core_router)
        app.include_router(goals_router)
        app.include_router(projects_router)

        async def override_db():
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
            db.execute = AsyncMock(return_value=result)
            db.get = AsyncMock(return_value=None)
            yield db

        async def override_org(org_id=None, db=None):
            org = MagicMock()
            org.id = ORG_ID
            return org

        user = _make_user(user_email) if user_email else None
        member = _make_member(member_role, user_id=user.id if user else None)

        async def override_member():
            return member

        async def override_user():
            return user

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_org] = override_org
        app.dependency_overrides[get_current_member] = override_member
        app.dependency_overrides[get_current_user] = override_user
        return app

    return _build


def test_engineer_cannot_delete_goal(app_with_member, monkeypatch):
    """RoleType.ENGINEER is not in GOALS_ROLES → 403."""
    # Admin bypass relies on settings.get_admin_emails(); make sure our user isn't in it
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "")
    app = app_with_member(RoleType.ENGINEER)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.delete(f"/api/orgs/{ORG_ID}/goals/{uuid.uuid4()}")
    assert resp.status_code == 403, resp.text


def test_pm_can_delete_goal(app_with_member, monkeypatch):
    """RoleType.PM is in GOALS_ROLES → passes role check (then hits a 404 because fixture returns no goal)."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "")
    app = app_with_member(RoleType.PM)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.delete(f"/api/orgs/{ORG_ID}/goals/{uuid.uuid4()}")
    # Role check passed if we're not 403. Handler body may 500 with mocked DB.
    assert resp.status_code != 403, resp.text


def test_admin_email_bypasses_role_check(app_with_member, monkeypatch):
    """A user with ENGINEER role but in ADMIN_EMAILS still passes role-gated endpoints."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "admin@example.com")
    app = app_with_member(RoleType.ENGINEER, user_email="admin@example.com")
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.delete(f"/api/orgs/{ORG_ID}/goals/{uuid.uuid4()}")
    # Role check passed if we're not 403. Handler body may 500 with mocked DB.
    assert resp.status_code != 403, resp.text


def test_engineer_cannot_create_member(app_with_member, monkeypatch):
    """create_member requires ADMIN_ROLES."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "")
    app = app_with_member(RoleType.ENGINEER)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/api/orgs/{ORG_ID}/members",
        json={"email": "new@example.com", "display_name": "New", "role": "engineer"},
    )
    assert resp.status_code == 403, resp.text


def test_cto_can_create_member(app_with_member, monkeypatch):
    """RoleType.CTO is in ADMIN_ROLES → role check passes."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "")
    app = app_with_member(RoleType.CTO)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/api/orgs/{ORG_ID}/members",
        json={"email": "new@example.com", "display_name": "New", "role": "engineer"},
    )
    # Fixture DB doesn't actually persist, so expect 422/500 from handler body - NOT 403
    assert resp.status_code != 403, resp.text


def test_engineer_cannot_merge_people(app_with_member, monkeypatch):
    """merge_people is admin-only."""
    from src.config import settings

    monkeypatch.setattr(settings, "admin_emails", "")
    app = app_with_member(RoleType.ENGINEER)
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.post(
        f"/api/orgs/{ORG_ID}/people/merge"
        f"?primary_id={uuid.uuid4()}&duplicate_id={uuid.uuid4()}"
    )
    assert resp.status_code == 403, resp.text


def test_require_role_sets_cover_all_destructive_mutations():
    """Sanity: the role sets we apply to mutations are well-formed."""
    assert RoleType.CTO in GOALS_ROLES
    assert RoleType.ENGINEER not in GOALS_ROLES
    assert RoleType.ENGINEER not in ADMIN_ROLES
    assert RoleType.CTO in ADMIN_ROLES
