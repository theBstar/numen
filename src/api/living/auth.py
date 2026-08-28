"""Living Mac app SSO.

Flow:
  1. Mac app deep-links Numen at GET /api/living/auth/mac, passing the user's
     existing Numen JWT in the Authorization header (the user has already
     completed Google SSO inside the embedded webview / browser).
  2. We verify the JWT, mint a long-lived MCP API key scoped to (org_id,
     user_id), and 302-redirect to ``living://auth/callback?token=<key>``.
  3. The Mac app captures the deep-link, stores the token in macOS Keychain,
     and uses it for subsequent /api/living/* and /mcp calls.

Reuses src/mcp/auth.create_api_key (NumenTokenVerifier already validates it)
so we never roll our own auth.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.mcp.auth import create_api_key
from src.shared.models import OrgMember, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/living/auth", tags=["living"])


DEFAULT_REDIRECT_URI = "living://auth/callback"


@router.get("/mac")
async def mac_sso(
    redirect_uri: str = Query(default=DEFAULT_REDIRECT_URI),
    org_id: UUID | None = Query(default=None),
    authorization: str = Header(default=None, alias="Authorization"),
    accept: str = Header(default="text/html", alias="Accept"),
    db: AsyncSession = Depends(get_db),
):
    """Mint a Living MCP key for the authenticated user and redirect to the
    Mac app's deep-link callback with ``?token=<numen_...>``.

    Only the ``living://`` scheme (or an explicit allowlist in production) is
    accepted as the redirect target.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    if not redirect_uri.startswith("living://"):
        raise HTTPException(
            status_code=400,
            detail="redirect_uri must use the living:// scheme",
        )

    # Verify the user JWT via the existing user_auth helper.
    from src.api.user_auth import decode_token

    payload = decode_token(authorization[7:])
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id = UUID(str(payload["sub"]))

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Resolve which org the key should be scoped to. If the user gave an
    # explicit ?org_id and is a member, use it; otherwise use the first
    # membership.
    members = list(
        (
            await db.execute(
                select(OrgMember).where(OrgMember.user_id == user_id)
            )
        ).scalars().all()
    )
    if not members:
        raise HTTPException(status_code=403, detail="User is not a member of any org")

    if org_id is not None:
        if not any(m.org_id == org_id for m in members):
            # Cross-org leak guard: never reveal which orgs the user CAN access.
            raise HTTPException(status_code=404, detail="Org not found")
        scoped_org_id = org_id
    else:
        scoped_org_id = members[0].org_id

    plaintext, _ = await create_api_key(
        db,
        org_id=scoped_org_id,
        name="Living Mac app",
        user_id=user_id,
    )
    await db.commit()

    sep = "&" if "?" in redirect_uri else "?"
    full_redirect = f"{redirect_uri}{sep}token={plaintext}"

    # Content negotiation: callers that send Accept: application/json get a
    # JSON body they can use to do `window.location = redirect_uri` from the
    # frontend page. Default (browser navigation) keeps the 302 behaviour.
    if "application/json" in (accept or "").lower():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"token": plaintext, "redirect_uri": full_redirect}
        )

    return RedirectResponse(url=full_redirect, status_code=302)



# ── Web SSO (WS3): for Claude Code / Conductor / Cursor / etc. ─────────


_KNOWN_WEB_CLIENTS = {"claude_code", "conductor", "cursor", "windsurf", "claude_desktop"}
DEFAULT_WEB_EXPIRY_DAYS = 90


def _install_snippet(client: str, plaintext: str, mcp_url: str) -> dict:
    """Per-client copy-paste install instructions. Mirrors mcp-config.ts shapes
    but targets command-line / config-file workflows for headless clients.
    """
    auth_header = f"Bearer {plaintext}"
    if client == "claude_code":
        return {
            "command": (
                f"claude mcp add numen --transport http "
                f"--url '{mcp_url}' --header 'Authorization: {auth_header}'"
            ),
            "kind": "cli",
        }
    if client == "conductor":
        return {
            "command": (
                f"conductor mcp add numen --url '{mcp_url}' "
                f"--header 'Authorization: {auth_header}'"
            ),
            "kind": "cli",
            "note": "Conductor MCP support arrived in v1.x; older builds need manual config.",
        }
    if client == "cursor":
        return {
            "config_path": "~/.cursor/mcp.json (or via Settings -> MCP Servers)",
            "config_json": {
                "mcpServers": {
                    "numen": {
                        "url": mcp_url,
                        "headers": {"Authorization": auth_header},
                    }
                }
            },
            "kind": "config_file",
        }
    if client == "claude_desktop":
        return {
            "config_path": "~/Library/Application Support/Claude/claude_desktop_config.json",
            "config_json": {
                "mcpServers": {
                    "numen": {
                        "url": mcp_url,
                        "headers": {"Authorization": auth_header},
                    }
                }
            },
            "kind": "config_file",
        }
    if client == "windsurf":
        return {
            "config_path": "Windsurf Settings -> MCP",
            "config_json": {
                "mcpServers": {
                    "numen": {
                        "url": mcp_url,
                        "headers": {"Authorization": auth_header},
                    }
                }
            },
            "kind": "config_file",
        }
    return {"raw_header": f"Authorization: {auth_header}", "kind": "manual"}


def _web_sso_response_headers() -> dict:
    """Security headers for the web-SSO mint response: never cached, never
    leaked via Referer, never embedded in another origin's frame."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Referrer-Policy": "no-referrer",
        "X-Frame-Options": "DENY",
        "Content-Security-Policy": "frame-ancestors 'none'",
    }


@router.post("/web")
async def web_sso(
    client: str = Query(..., description="Agent client: claude_code|conductor|cursor|claude_desktop|windsurf"),
    org_id: UUID | None = Query(default=None),
    expires_in_days: int = Query(default=DEFAULT_WEB_EXPIRY_DAYS, ge=1, le=365),
    authorization: str = Header(default=None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
):
    """Mint a Numen MCP API key for a non-Mac agent client and return install instructions.

    POST (not GET) to avoid drive-by minting via link click. Requires a
    user JWT (the user is logged into the Numen web app). Response is
    JSON with the plaintext key (shown once - the page must consume it
    immediately) plus a per-client install snippet.

    Security headers force no-store / no-referrer / frame-ancestors none.
    The HTTP method (POST) is the CSRF defense; the JWT cookie + same-site
    policy keeps this safe from cross-origin POSTs.
    """
    from fastapi.responses import JSONResponse

    if client not in _KNOWN_WEB_CLIENTS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"client must be one of {sorted(_KNOWN_WEB_CLIENTS)} "
                f"(got {client!r})"
            ),
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")

    from src.api.user_auth import decode_token

    payload = decode_token(authorization[7:])
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")
    user_id = UUID(str(payload["sub"]))

    user = (
        await db.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    members = list(
        (
            await db.execute(select(OrgMember).where(OrgMember.user_id == user_id))
        ).scalars().all()
    )
    if not members:
        raise HTTPException(status_code=403, detail="User is not a member of any org")

    if org_id is not None:
        if not any(m.org_id == org_id for m in members):
            raise HTTPException(status_code=404, detail="Org not found")
        scoped_org_id = org_id
    else:
        scoped_org_id = members[0].org_id

    plaintext, api_key = await create_api_key(
        db,
        org_id=scoped_org_id,
        name=f"Numen MCP for {client}",
        user_id=user_id,
        expires_in_days=expires_in_days,
    )
    await db.commit()

    # Compute the full MCP URL from the request host. Importing settings late
    # to avoid circular imports.
    from src.config import settings

    mcp_url = f"{settings.app_url.rstrip('/')}/mcp"

    body = {
        "client": client,
        "key": {
            "id": str(api_key.id),
            "plaintext": plaintext,
            "name": api_key.name,
            "expires_at": api_key.expires_at.isoformat() if api_key.expires_at else None,
        },
        "mcp_url": mcp_url,
        "install": _install_snippet(client, plaintext, mcp_url),
        "instructions": [
            "Copy the install snippet above to your client's MCP config.",
            "Restart the client (Claude Code, Conductor, etc.).",
            "In your agent: ask it to call hello_numen first.",
            f"Key expires {api_key.expires_at.isoformat() if api_key.expires_at else 'never'}.",
            "Save this key now - it won't be shown again. Manage at /account/keys.",
        ],
    }

    return JSONResponse(content=body, headers=_web_sso_response_headers())
