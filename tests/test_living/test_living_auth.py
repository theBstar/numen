"""Tests for /api/living/auth/mac SSO endpoint."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.living import auth_router

USER_ID = uuid.UUID("00000000-0000-0000-0000-0000000000c3")
ORG_A = uuid.UUID("00000000-0000-0000-0000-0000000000a1")


def _scalar(value):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=value)
    res.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[value] if value else [])))
    return res


def _build_app(user=None, members=None):
    app = FastAPI()
    app.include_router(auth_router)

    async def override_db():
        db = AsyncMock()
        responses = [
            _scalar(user),
            _scalar(members[0] if members else None),
        ]
        # The members query uses .scalars().all() — set it up specifically.
        if members is not None:
            members_res = MagicMock()
            members_res.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=members))
            )
            responses[1] = members_res

        async def _execute(stmt):
            return responses.pop(0) if responses else _scalar(None)

        db.execute = AsyncMock(side_effect=_execute)
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        yield db

    app.dependency_overrides[get_db] = override_db
    return app


def test_mac_sso_redirects_with_token():
    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    member = MagicMock()
    member.org_id = ORG_A
    member.user_id = USER_ID

    app = _build_app(user=user, members=[member])
    with (
        patch(
            "src.api.user_auth.decode_token",
            return_value={"sub": str(USER_ID), "type": "access"},
        ),
        patch(
            "src.api.living.auth.create_api_key",
            new=AsyncMock(return_value=("numen_test_key_123", MagicMock())),
        ),
    ):
        with TestClient(app) as c:
            r = c.get(
                "/api/living/auth/mac",
                headers={"Authorization": "Bearer fake.jwt"},
                follow_redirects=False,
            )
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("living://auth/callback")
    assert "token=numen_test_key_123" in loc


def test_mac_sso_rejects_non_living_redirect():
    app = _build_app()
    with patch(
        "src.api.user_auth.decode_token",
        return_value={"sub": str(USER_ID), "type": "access"},
    ):
        with TestClient(app) as c:
            r = c.get(
                "/api/living/auth/mac?redirect_uri=https://evil.example/callback",
                headers={"Authorization": "Bearer fake.jwt"},
                follow_redirects=False,
            )
    assert r.status_code == 400


def test_mac_sso_requires_auth_header():
    app = _build_app()
    with TestClient(app) as c:
        r = c.get("/api/living/auth/mac")
    assert r.status_code == 401


def test_mac_sso_404_when_org_id_not_a_member():
    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    member = MagicMock()
    member.org_id = ORG_A
    member.user_id = USER_ID

    app = _build_app(user=user, members=[member])
    with patch(
        "src.api.user_auth.decode_token",
        return_value={"sub": str(USER_ID), "type": "access"},
    ):
        with TestClient(app) as c:
            r = c.get(
                f"/api/living/auth/mac?org_id={uuid.uuid4()}",
                headers={"Authorization": "Bearer fake.jwt"},
                follow_redirects=False,
            )
    assert r.status_code == 404
