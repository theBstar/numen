"""The account-keys routes must reject anonymous callers, not crash on them.

They depended on `get_current_user`, which deliberately returns None when there
is no Authorization header, but annotated the parameter as `User` and
dereferenced it. Against a live stack an unauthenticated GET /api/account/keys
returned 500 (AttributeError: 'NoneType' object has no attribute 'id') instead
of 401. `get_current_user_required` already existed for exactly this.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.routes_account_keys import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)

    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/account/keys"),
        ("post", "/api/account/keys"),
        ("delete", "/api/account/keys/00000000-0000-0000-0000-000000000001"),
        ("post", "/api/account/keys/00000000-0000-0000-0000-000000000001/rotate"),
    ],
)
def test_anonymous_gets_401_not_500(client, method, path):
    kwargs = {"json": {}} if method == "post" else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code != 500, f"{method.upper()} {path} crashed on an anonymous caller"
    assert resp.status_code == 401
