"""Tests for the surface-agnostic caller identity."""

import uuid

import pytest

from src.agent.principal import Audience, Principal, Surface


def _principal(**overrides):
    base = {
        "org_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "email": "someone@example.com",
        "surface": Surface.WEB,
    }
    base.update(overrides)
    return Principal(**base)


def test_principal_carries_org_and_identity():
    org_id = uuid.uuid4()
    p = _principal(org_id=org_id)
    assert p.org_id == org_id
    assert p.email == "someone@example.com"


def test_write_requires_a_bound_user():
    """An unbound credential is read-only, matching the MCP key model."""
    assert _principal().can_write is True
    assert _principal(user_id=None).can_write is False


def test_private_audience_allows_private_grounding():
    p = _principal(audience=Audience.PRIVATE)
    assert p.can_access_private_data is True


def test_shared_audience_blocks_private_grounding():
    """In a public channel the answer is visible to people who may not have
    access to the underlying records, so ground only on public data."""
    p = _principal(surface=Surface.SLACK, audience=Audience.SHARED)
    assert p.can_access_private_data is False


def test_default_audience_is_private():
    """Web and DM surfaces address one person; that is the safe default."""
    assert _principal().audience is Audience.PRIVATE


def test_shared_audience_also_blocks_writes():
    """A public channel must not be able to mutate records on someone's behalf."""
    p = _principal(surface=Surface.SLACK, audience=Audience.SHARED)
    assert p.can_write is False


def test_principal_is_immutable():
    p = _principal()
    with pytest.raises(Exception):
        p.org_id = uuid.uuid4()


def test_display_name_falls_back_to_email_local_part():
    assert _principal(email="ada@example.com").display_name == "ada"
    assert _principal(email="ada@example.com", name="Ada Lovelace").display_name == "Ada Lovelace"
