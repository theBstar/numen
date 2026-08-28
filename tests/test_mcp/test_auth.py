"""Tests for MCP API key authentication."""

import hashlib
import uuid
from unittest.mock import AsyncMock, MagicMock

from src.mcp.auth import _hash_key, create_api_key, revoke_api_key, validate_api_key
from src.mcp.token_verifier import decode_client_id, encode_client_id
from tests.conftest import TEST_ORG_ID


def test_hash_key_is_deterministic():
    assert _hash_key("test") == _hash_key("test")
    assert _hash_key("test") == hashlib.sha256(b"test").hexdigest()


def test_hash_key_differs_for_different_keys():
    assert _hash_key("key1") != _hash_key("key2")


async def test_create_api_key_without_user_id_is_legacy(mock_db):
    plaintext, api_key = await create_api_key(mock_db, TEST_ORG_ID, "test key")

    assert plaintext.startswith("numen_")
    assert api_key.org_id == TEST_ORG_ID
    assert api_key.user_id is None
    assert api_key.name == "test key"
    assert api_key.key_hash == _hash_key(plaintext)
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


async def test_create_api_key_with_user_id_binds_actor(mock_db):
    user_id = uuid.uuid4()
    plaintext, api_key = await create_api_key(
        mock_db, TEST_ORG_ID, "bound key", user_id=user_id
    )
    assert plaintext.startswith("numen_")
    assert api_key.user_id == user_id


async def test_validate_api_key_returns_org_and_user(mock_db):
    user_id = uuid.uuid4()
    plaintext, api_key = await create_api_key(
        mock_db, TEST_ORG_ID, "test key", user_id=user_id
    )

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute = AsyncMock(return_value=mock_result)

    validated = await validate_api_key(mock_db, plaintext)
    assert validated == (TEST_ORG_ID, user_id)


async def test_validate_api_key_legacy_key_has_none_user(mock_db):
    plaintext, api_key = await create_api_key(mock_db, TEST_ORG_ID, "legacy")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = api_key
    mock_db.execute = AsyncMock(return_value=mock_result)

    validated = await validate_api_key(mock_db, plaintext)
    assert validated == (TEST_ORG_ID, None)


async def test_validate_api_key_returns_none_for_invalid_key(mock_db):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    assert await validate_api_key(mock_db, "numen_invalid_key") is None


async def test_revoke_api_key_returns_true_when_found(mock_db):
    key_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.rowcount = 1
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await revoke_api_key(mock_db, key_id, TEST_ORG_ID)
    assert result is True


async def test_revoke_api_key_returns_false_when_not_found(mock_db):
    key_id = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.rowcount = 0
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await revoke_api_key(mock_db, key_id, TEST_ORG_ID)
    assert result is False


def test_client_id_round_trip_with_user():
    org = str(uuid.uuid4())
    user = str(uuid.uuid4())
    encoded = encode_client_id(org, user)
    assert decode_client_id(encoded) == (org, user)


def test_client_id_round_trip_legacy():
    org = str(uuid.uuid4())
    encoded = encode_client_id(org, None)
    assert decode_client_id(encoded) == (org, None)
