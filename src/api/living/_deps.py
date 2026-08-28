"""Shared dependencies for the Living API package.

The Living endpoints accept either:
  - A Numen MCP API key as `Authorization: Bearer <numen_...>` (used by the
    Mac app once it has completed SSO and stored the key in macOS Keychain).
  - A standard Numen JWT access token (for browser-based callers, e.g. the
    settings UI).

In both cases the dependency resolves to ``LivingPrincipal(org_id, user_id)``.
Org_id is the universal tenant boundary and is never accepted from the URL or
the request body.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.mcp.auth import validate_api_key
from src.shared.models import OrgMember, User


@dataclass(frozen=True)
class LivingPrincipal:
    org_id: UUID
    user_id: UUID | None
    # When the principal authed via API key, this is the key's id; useful
    # for audit logs but not load-bearing for authorization.
    via_api_key: bool = False


async def get_living_principal(
    authorization: str = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> LivingPrincipal:
    """Resolve a Living API caller to (org_id, user_id).

    Tries the Numen MCP API key first (``numen_*`` shape), then falls back to
    the JWT bearer token used by the web UI.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    token = authorization[7:]

    # Strategy 1: MCP API key (Mac app).
    if token.startswith("numen_"):
        validated = await validate_api_key(db, token)
        if validated is None:
            raise HTTPException(status_code=401, detail="Invalid or revoked API key")
        org_id, user_id = validated
        await db.commit()  # persist last_used_at update
        return LivingPrincipal(org_id=org_id, user_id=user_id, via_api_key=True)

    # Strategy 2: JWT (web UI).
    from src.api.user_auth import decode_token

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id = UUID(str(payload["sub"]))
    user_row = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if not user_row or not user_row.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    # Resolve the user's primary org membership. If the user belongs to multiple
    # orgs, the request must specify it via X-Numen-Org header.
    members_q = select(OrgMember).where(OrgMember.user_id == user_id)
    members = list((await db.execute(members_q)).scalars().all())
    if not members:
        raise HTTPException(status_code=403, detail="User is not a member of any org")
    org_id = members[0].org_id
    return LivingPrincipal(org_id=org_id, user_id=user_id, via_api_key=False)
