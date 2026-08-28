"""API key authentication for MCP server multi-tenancy."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import ApiKey


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def create_api_key(
    db: AsyncSession,
    org_id: UUID,
    name: str,
    user_id: UUID | None = None,
    expires_in_days: int | None = None,
) -> tuple[str, ApiKey]:
    """Create a new API key for an org. Returns (plaintext_key, api_key_row).

    user_id binds the key to the creating user so MCP write tools can attribute
    mutations. Legacy callers that omit it produce read-only keys.

    expires_in_days controls automatic expiry. None = no expiry (default for
    back-compat). Web-flow callers (WS3) pass 90 by default.
    """
    from datetime import timedelta

    plaintext = f"numen_{secrets.token_urlsafe(32)}"
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        if expires_in_days is not None
        else None
    )
    api_key = ApiKey(
        org_id=org_id,
        user_id=user_id,
        key_hash=_hash_key(plaintext),
        name=name,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()
    return plaintext, api_key


async def validate_api_key(
    db: AsyncSession, key: str
) -> tuple[UUID, UUID | None] | None:
    """Validate an API key and return (org_id, user_id), or None if invalid.

    user_id is None for legacy keys that predate the user_id column.
    """
    key_hash = _hash_key(key)
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    result = await db.execute(stmt)
    api_key = result.scalar_one_or_none()
    if api_key is None:
        return None

    # Honor expiry (WS3): expired keys behave like revoked keys.
    if api_key.expires_at is not None and api_key.expires_at < datetime.now(timezone.utc):
        return None

    # Update last_used_at
    await db.execute(update(ApiKey).where(ApiKey.id == api_key.id).values(last_used_at=datetime.now(timezone.utc)))
    return api_key.org_id, api_key.user_id


async def list_api_keys(db: AsyncSession, org_id: UUID) -> list[ApiKey]:
    """List all API keys for an org (never returns the key itself)."""
    stmt = select(ApiKey).where(ApiKey.org_id == org_id).order_by(ApiKey.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def revoke_api_key(db: AsyncSession, key_id: UUID, org_id: UUID) -> bool:
    """Revoke an API key. Returns True if found and revoked."""
    stmt = update(ApiKey).where(ApiKey.id == key_id, ApiKey.org_id == org_id).values(is_active=False)
    result = await db.execute(stmt)
    return result.rowcount > 0
