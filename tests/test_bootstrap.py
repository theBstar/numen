"""A fresh install must be usable without registering a Google OAuth app.

`docker compose up` produced a running stack with an empty database, and the
only sign-in route was Google OAuth. Nobody could create the first user, so the
documented quick start ended at a login screen that could not be passed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.bootstrap import BootstrapError, bootstrap_admin
from src.shared.types import RoleType


def _db(existing_user=None, existing_org=None, existing_member=None):
    """An AsyncSession whose three lookups return the given rows.

    Order matches bootstrap_admin: user, org, then member.
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()

    def result_for(row):
        r = MagicMock()
        r.scalar_one_or_none.return_value = row
        return r

    db.execute = AsyncMock(
        side_effect=[
            result_for(existing_user),
            result_for(existing_org),
            result_for(existing_member),
        ]
    )
    return db


@pytest.mark.asyncio
async def test_creates_org_user_member_and_key_on_an_empty_database():
    db = _db()

    result = await bootstrap_admin(db, email="ada@acme.com", org_name="Acme")

    assert result.api_key.startswith("numen_")
    assert result.org_id is not None
    assert result.user_id is not None
    assert result.created_org is True
    assert result.created_user is True

    added = [c.args[0] for c in db.add.call_args_list]
    kinds = {type(o).__name__ for o in added}
    assert {"Organization", "User", "OrgMember", "ApiKey"} <= kinds


@pytest.mark.asyncio
async def test_the_first_member_can_administer_the_org():
    """A key bound to an engineer could not connect sources or invite anyone."""
    db = _db()

    await bootstrap_admin(db, email="ada@acme.com", org_name="Acme")

    member = next(
        o for o in (c.args[0] for c in db.add.call_args_list)
        if type(o).__name__ == "OrgMember"
    )
    assert member.role is RoleType.CTO


@pytest.mark.asyncio
async def test_rerunning_reuses_the_existing_user_and_org():
    """Idempotent: running it twice must not fail or fork a second org."""
    user = MagicMock()
    user.id = uuid4()
    org = MagicMock()
    org.id = uuid4()

    db = _db(existing_user=user, existing_org=org)
    result = await bootstrap_admin(db, email="ada@acme.com", org_name="Acme")

    assert result.created_user is False
    assert result.created_org is False
    assert result.org_id == org.id
    assert result.user_id == user.id
    # Still mints a fresh key - the previous one was shown once and is gone.
    assert result.api_key.startswith("numen_")


@pytest.mark.asyncio
async def test_the_org_slug_comes_from_the_name():
    db = _db()
    await bootstrap_admin(db, email="ada@acme.com", org_name="Acme Rocket Co")

    org = next(
        o for o in (c.args[0] for c in db.add.call_args_list)
        if type(o).__name__ == "Organization"
    )
    assert org.slug == "acme-rocket-co"


@pytest.mark.asyncio
async def test_org_defaults_to_the_email_domain():
    db = _db()
    result = await bootstrap_admin(db, email="ada@acme.com")

    org = next(
        o for o in (c.args[0] for c in db.add.call_args_list)
        if type(o).__name__ == "Organization"
    )
    assert org.domain == "acme.com"
    assert result.org_name


@pytest.mark.asyncio
@pytest.mark.parametrize("email", ["", "not-an-email", "@acme.com", "ada@", "ada acme.com"])
async def test_a_malformed_address_is_refused(email):
    """The address becomes the org's admin identity - it has to be real."""
    with pytest.raises(BootstrapError):
        await bootstrap_admin(_db(), email=email)


@pytest.mark.asyncio
async def test_the_key_is_bound_to_the_user():
    """An unbound key is read-only, so the admin could not write anything."""
    db = _db()
    result = await bootstrap_admin(db, email="ada@acme.com")

    key = next(
        o for o in (c.args[0] for c in db.add.call_args_list)
        if type(o).__name__ == "ApiKey"
    )
    assert key.user_id == result.user_id
    assert key.org_id == result.org_id
