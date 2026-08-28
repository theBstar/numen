"""User-scoped API key management (WS3).

Powers the /account/keys page in the frontend: list-your-keys, mint a new
one, revoke. Sister to src/api/routes_api_keys.py which is org-path-bound;
this surface is per-user (any key the user created across their orgs).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, get_db
from src.mcp.auth import create_api_key, revoke_api_key
from src.shared.models import ApiKey, OrgMember, User

router = APIRouter(prefix="/api/account/keys", tags=["account"])

# WS3: web-flow keys default to 90-day expiry.
DEFAULT_EXPIRY_DAYS = 90


class KeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    org_id: UUID | None = None
    expires_in_days: int | None = Field(default=DEFAULT_EXPIRY_DAYS, ge=1, le=365)


class KeyOut(BaseModel):
    id: UUID
    name: str
    org_id: UUID
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None


class KeyMintOut(KeyOut):
    plaintext: str = Field(description="The API key. Shown only once.")


class KeyListOut(BaseModel):
    items: list[KeyOut]


def _to_out(k: ApiKey) -> KeyOut:
    return KeyOut(
        id=k.id,
        name=k.name,
        org_id=k.org_id,
        is_active=k.is_active,
        created_at=k.created_at,
        last_used_at=k.last_used_at,
        expires_at=k.expires_at,
    )


@router.get("", response_model=KeyListOut)
async def list_my_keys(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyListOut:
    """List all API keys created by the calling user, across all their orgs."""
    rows = (
        await db.execute(
            select(ApiKey)
            .where(ApiKey.user_id == user.id)
            .order_by(ApiKey.created_at.desc())
        )
    ).scalars().all()
    return KeyListOut(items=[_to_out(k) for k in rows])


@router.post("", response_model=KeyMintOut, status_code=201)
async def mint_key(
    body: KeyCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyMintOut:
    """Mint a new API key for the calling user. plaintext returned ONCE.

    org_id defaults to the user's first membership; if specified, the user
    must be a member of that org (else 404, never reveal cross-org existence).
    """
    members = (
        await db.execute(
            select(OrgMember).where(OrgMember.user_id == user.id)
        )
    ).scalars().all()
    if not members:
        raise HTTPException(status_code=403, detail="User has no org memberships")

    if body.org_id is not None:
        if not any(m.org_id == body.org_id for m in members):
            raise HTTPException(status_code=404, detail="Org not found")
        scoped_org = body.org_id
    else:
        scoped_org = members[0].org_id

    plaintext, api_key = await create_api_key(
        db,
        org_id=scoped_org,
        name=body.name,
        user_id=user.id,
        expires_in_days=body.expires_in_days,
    )
    await db.commit()
    return KeyMintOut(plaintext=plaintext, **_to_out(api_key).model_dump())


@router.delete("/{key_id}", status_code=204)
async def revoke_my_key(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Revoke a specific key. Must belong to the calling user."""
    key = (
        await db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
        )
    ).scalar_one_or_none()
    if key is None:
        # Cross-user leak guard: pretend it doesn't exist.
        raise HTTPException(status_code=404, detail="Key not found")
    revoked = await revoke_api_key(db, key_id, key.org_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="Key not found")
    await db.commit()


@router.post("/{key_id}/rotate", response_model=KeyMintOut)
async def rotate_my_key(
    key_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KeyMintOut:
    """Atomic rotate: revoke the old key, mint a new one with same name+org+expiry.

    Returns the new plaintext (shown once). The old key stops working
    immediately; callers should wire the new one before the next request.
    """
    old = (
        await db.execute(
            select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user.id)
        )
    ).scalar_one_or_none()
    if old is None:
        raise HTTPException(status_code=404, detail="Key not found")

    # Compute expiry days from the old key's window if any
    expires_in_days: int | None = None
    if old.expires_at is not None:
        # Use the same nominal window from now (not the literal old expiry)
        expires_in_days = DEFAULT_EXPIRY_DAYS

    plaintext, new_key = await create_api_key(
        db,
        org_id=old.org_id,
        name=old.name,
        user_id=user.id,
        expires_in_days=expires_in_days,
    )
    await revoke_api_key(db, key_id, old.org_id)
    await db.commit()
    return KeyMintOut(plaintext=plaintext, **_to_out(new_key).model_dump())
