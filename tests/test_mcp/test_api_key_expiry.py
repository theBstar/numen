"""Tests for WS3: API key expiry-aware create + validate."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

from src.mcp.auth import create_api_key, validate_api_key
from tests.conftest import TEST_ORG_ID


async def test_create_api_key_no_expiry_by_default(mock_db):
    plaintext, api_key = await create_api_key(mock_db, TEST_ORG_ID, "no-exp")
    assert api_key.expires_at is None


async def test_create_api_key_with_expiry_sets_future_timestamp(mock_db):
    plaintext, api_key = await create_api_key(
        mock_db, TEST_ORG_ID, "expires", expires_in_days=90
    )
    assert api_key.expires_at is not None
    delta = api_key.expires_at - datetime.now(timezone.utc)
    # 90 days +/- a few seconds
    assert timedelta(days=89, hours=23) < delta < timedelta(days=90, hours=1)


async def test_validate_api_key_returns_none_for_expired_key(mock_db):
    """Expired keys are treated like revoked keys - return None."""
    plaintext, api_key = await create_api_key(
        mock_db, TEST_ORG_ID, "expired-already"
    )
    # Force expiry in the past
    api_key.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
    api_key.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute = AsyncMock(return_value=mock_result)

    out = await validate_api_key(mock_db, plaintext)
    assert out is None


async def test_validate_api_key_succeeds_for_unexpired_key(mock_db):
    user_id = uuid.uuid4()
    plaintext, api_key = await create_api_key(
        mock_db, TEST_ORG_ID, "fresh", user_id=user_id, expires_in_days=30
    )
    api_key.is_active = True

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute = AsyncMock(return_value=mock_result)

    out = await validate_api_key(mock_db, plaintext)
    assert out == (TEST_ORG_ID, user_id)


async def test_validate_api_key_no_expiry_succeeds(mock_db):
    """Legacy keys with NULL expires_at must still validate (back-compat)."""
    plaintext, api_key = await create_api_key(mock_db, TEST_ORG_ID, "legacy")
    api_key.is_active = True
    api_key.expires_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute = AsyncMock(return_value=mock_result)

    out = await validate_api_key(mock_db, plaintext)
    assert out == (TEST_ORG_ID, None)
