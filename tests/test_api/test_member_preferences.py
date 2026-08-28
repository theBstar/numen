"""Tests for the briefing-time / briefing-channel member preferences."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.api.schemas import MemberUpdateRequest


def test_briefing_hour_accepts_valid_range():
    req = MemberUpdateRequest(briefing_hour=0)
    assert req.briefing_hour == 0
    req = MemberUpdateRequest(briefing_hour=23)
    assert req.briefing_hour == 23


def test_briefing_hour_rejects_24():
    with pytest.raises(ValidationError):
        MemberUpdateRequest(briefing_hour=24)


def test_briefing_hour_rejects_negative():
    with pytest.raises(ValidationError):
        MemberUpdateRequest(briefing_hour=-1)


def test_briefing_channel_accepts_email_and_slack():
    assert MemberUpdateRequest(briefing_channel="email").briefing_channel == "email"
    assert MemberUpdateRequest(briefing_channel="slack").briefing_channel == "slack"


def test_briefing_channel_rejects_other_values():
    with pytest.raises(ValidationError):
        MemberUpdateRequest(briefing_channel="sms")


def test_member_update_allows_all_fields_optional():
    req = MemberUpdateRequest()
    assert req.briefing_hour is None
    assert req.briefing_channel is None
