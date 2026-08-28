"""Tests for mapping a Slack user onto a Numen principal."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.principal import Audience, Surface
from src.slack.identity import principal_for_slack_user


def _member(email="ada@example.com"):
    member = MagicMock()
    member.id = uuid.uuid4()
    member.user_id = uuid.uuid4()
    member.email = email
    member.display_name = "Ada Lovelace"
    return member


@pytest.mark.asyncio
async def test_maps_slack_user_to_member_by_email():
    org_id = uuid.uuid4()
    member = _member()

    with patch("src.slack.identity.lookup_slack_email", new=AsyncMock(return_value="ada@example.com")), patch(
        "src.slack.identity.find_member_by_email", new=AsyncMock(return_value=member)
    ):
        principal = await principal_for_slack_user(
            AsyncMock(), org_id, slack_user_id="U123", is_direct_message=True
        )

    assert principal is not None
    assert principal.org_id == org_id
    assert principal.email == "ada@example.com"
    assert principal.surface is Surface.SLACK
    assert principal.member_id == member.id


@pytest.mark.asyncio
async def test_direct_message_is_a_private_audience():
    with patch("src.slack.identity.lookup_slack_email", new=AsyncMock(return_value="ada@example.com")), patch(
        "src.slack.identity.find_member_by_email", new=AsyncMock(return_value=_member())
    ):
        principal = await principal_for_slack_user(
            AsyncMock(), uuid.uuid4(), slack_user_id="U123", is_direct_message=True
        )

    assert principal.audience is Audience.PRIVATE
    assert principal.can_access_private_data is True
    assert principal.can_write is True


@pytest.mark.asyncio
async def test_channel_is_a_shared_audience():
    """Others can read a channel, so no private grounding and no writes."""
    with patch("src.slack.identity.lookup_slack_email", new=AsyncMock(return_value="ada@example.com")), patch(
        "src.slack.identity.find_member_by_email", new=AsyncMock(return_value=_member())
    ):
        principal = await principal_for_slack_user(
            AsyncMock(), uuid.uuid4(), slack_user_id="U123", is_direct_message=False
        )

    assert principal.audience is Audience.SHARED
    assert principal.can_access_private_data is False
    assert principal.can_write is False


@pytest.mark.asyncio
async def test_unknown_slack_user_gets_no_principal():
    """Someone with no Numen account must not inherit org-wide access."""
    with patch("src.slack.identity.lookup_slack_email", new=AsyncMock(return_value="stranger@example.com")), patch(
        "src.slack.identity.find_member_by_email", new=AsyncMock(return_value=None)
    ):
        principal = await principal_for_slack_user(
            AsyncMock(), uuid.uuid4(), slack_user_id="U999", is_direct_message=True
        )

    assert principal is None


@pytest.mark.asyncio
async def test_slack_lookup_failure_gets_no_principal():
    with patch("src.slack.identity.lookup_slack_email", new=AsyncMock(return_value=None)):
        principal = await principal_for_slack_user(
            AsyncMock(), uuid.uuid4(), slack_user_id="U999", is_direct_message=True
        )

    assert principal is None
