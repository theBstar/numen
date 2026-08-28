"""Tests for briefing delivery module."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.briefing.delivery import record_briefing, send_briefing_email
from src.shared.types import BriefingItem, DeliveryStatus, EntityType


@pytest.mark.asyncio
async def test_record_briefing_creates_db_record():
    """record_briefing should add a Briefing row to the session."""
    db = AsyncMock()
    db.add = MagicMock()

    member_id = uuid.uuid4()
    items = [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="Test task",
            why_it_matters="Important",
            urgency_score=0.8,
        ),
    ]

    briefing = await record_briefing(db, member_id, items, DeliveryStatus.SENT, org_id=uuid.uuid4())

    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert briefing.org_member_id == member_id
    assert briefing.delivery_status == DeliveryStatus.SENT
    assert briefing.content["item_count"] == 1


@pytest.mark.asyncio
async def test_record_briefing_pending_no_delivered_at():
    """A PENDING briefing should have delivered_at = None."""
    db = AsyncMock()
    db.add = MagicMock()

    briefing = await record_briefing(db, uuid.uuid4(), [], DeliveryStatus.PENDING, org_id=uuid.uuid4())
    assert briefing.delivered_at is None


@pytest.mark.asyncio
async def test_record_briefing_sent_has_delivered_at():
    """A SENT briefing should have delivered_at set."""
    db = AsyncMock()
    db.add = MagicMock()

    briefing = await record_briefing(db, uuid.uuid4(), [], DeliveryStatus.SENT, org_id=uuid.uuid4())
    assert briefing.delivered_at is not None


@pytest.mark.asyncio
async def test_record_briefing_empty_items():
    """Should handle empty items list gracefully."""
    db = AsyncMock()
    db.add = MagicMock()

    briefing = await record_briefing(db, uuid.uuid4(), [], DeliveryStatus.SENT, org_id=uuid.uuid4())
    assert briefing.content["item_count"] == 0
    assert briefing.content["items"] == []


@pytest.mark.asyncio
async def test_send_briefing_email_success():
    """send_briefing_email should return True on success."""
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(return_value={"id": "test-email-id"})

    with patch("src.briefing.delivery.asyncio.get_event_loop", return_value=mock_loop):
        result = await send_briefing_email(
            to_email="test@example.com",
            subject="Test Briefing",
            html="<h1>Test</h1>",
            text="Test",
        )

    assert result is True


@pytest.mark.asyncio
async def test_send_briefing_email_failure_all_retries():
    """send_briefing_email should return False after all retries fail."""
    mock_loop = MagicMock()
    mock_loop.run_in_executor = AsyncMock(side_effect=Exception("API error"))

    with patch("src.briefing.delivery.asyncio.get_event_loop", return_value=mock_loop):
        with patch("src.briefing.delivery.asyncio.sleep", new_callable=AsyncMock):
            result = await send_briefing_email(
                to_email="test@example.com",
                subject="Test",
                html="<h1>Test</h1>",
                text="Test",
            )

    assert result is False
