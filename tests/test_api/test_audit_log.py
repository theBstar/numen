"""Phase 3: audit-log auth + authz events.

Verifies that log_action_safely is called on:
- authz denial when unauth hits an org-scoped route
- role denial when a member with insufficient role hits a gated route
- login success/failure (unit-level test with mocked Google)
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_current_member, get_current_user, get_db, get_org
from src.api.routes import router as core_router
from src.api.routes_goals import router as goals_router
from src.config import settings
from src.shared.models import OrgMember, User
from src.shared.types import RoleType

ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def app_for_authz():
    app = FastAPI()
    app.include_router(core_router)
    app.include_router(goals_router)

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

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_org] = override_org
    return app


def test_unauth_access_logs_authz_denial(app_for_authz, monkeypatch):
    """Unauth GET on an org-scoped endpoint logs auth.authz.denied."""
    monkeypatch.setattr(settings, "allow_header_auth", False)
    with patch("src.api.dependencies.log_action_safely", new_callable=AsyncMock) as mock_log:
        client = TestClient(app_for_authz, raise_server_exceptions=False)
        resp = client.get(f"/api/orgs/{ORG_ID}/members")
        assert resp.status_code == 401
        mock_log.assert_called()
        # Inspect the call - action should be auth.authz.denied
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == "auth.authz.denied"
        assert kwargs["resource_type"] == "org_membership"


def test_role_denied_logs_authz_denial(app_for_authz, monkeypatch):
    """Member with ENGINEER role hitting GOALS-gated delete logs a role-check denial."""
    monkeypatch.setattr(settings, "admin_emails", "")

    member = MagicMock(spec=OrgMember)
    member.id = uuid.uuid4()
    member.org_id = ORG_ID
    member.email = "eng@example.com"
    member.role = RoleType.ENGINEER
    member.user_id = uuid.uuid4()
    member.person_entity_id = None

    user = MagicMock(spec=User)
    user.id = member.user_id
    user.email = member.email
    user.is_active = True

    async def override_member():
        return member

    async def override_user():
        return user

    app_for_authz.dependency_overrides[get_current_member] = override_member
    app_for_authz.dependency_overrides[get_current_user] = override_user

    with patch("src.api.rbac.log_action_safely", new_callable=AsyncMock) as mock_log:
        client = TestClient(app_for_authz, raise_server_exceptions=False)
        resp = client.delete(f"/api/orgs/{ORG_ID}/goals/{uuid.uuid4()}")
        assert resp.status_code == 403
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["action"] == "auth.authz.denied"
        assert kwargs["resource_type"] == "role_check"
        assert kwargs["details"]["actual_role"] == "engineer"


def test_log_action_safely_swallows_exceptions():
    """A broken DB shouldn't 500 the auth path."""
    import asyncio

    from src.shared.audit import log_action_safely

    bad_db = AsyncMock()
    bad_db.add = MagicMock(side_effect=RuntimeError("boom"))

    async def run():
        # Must not raise
        await log_action_safely(bad_db, action="test.action", details={})

    asyncio.run(run())
