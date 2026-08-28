"""OAuth flow handlers for Linear, GitHub, and Slack."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.analytics.events import track_connector_connected
from src.api.dependencies import get_db
from src.api.schemas import (
    ErrorResponse,
    OAuthCallbackResponse,
    OAuthConnectResponse,
    OAuthDisconnectResponse,
)
from src.config import settings
from src.shared.audit import log_action_safely
from src.shared.models import OAuthToken, Organization
from src.shared.types import SourceType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# ── OAuth URLs ─────────────────────────────────────────────────────────

OAUTH_CONFIG = {
    "linear": {
        "authorize_url": "https://linear.app/oauth/authorize",
        "token_url": "https://api.linear.app/oauth/token",
        "scopes": "read",
        "client_id": lambda: settings.linear_client_id,
        "client_secret": lambda: settings.linear_client_secret,
    },
    "github": {
        "authorize_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "scopes": "repo read:org read:user",
        "client_id": lambda: settings.github_client_id,
        "client_secret": lambda: settings.github_client_secret,
    },
    "slack": {
        "authorize_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        # Bot token scopes. Beyond ingestion and briefing DMs, the agent needs
        # to be addressed (app_mentions:read, im:history) and to show progress
        # in the assistant pane (assistant:write).
        "scopes": (
            "app_mentions:read,assistant:write,chat:write,im:history,im:write,"
            "users:read,users:read.email,channels:history,channels:read,reactions:read"
        ),
        # User token scopes -- preserved for inbound APIs that require a user context.
        "user_scopes": "channels:history,channels:read,users:read,users:read.email,reactions:read",
        "client_id": lambda: settings.slack_client_id,
        "client_secret": lambda: settings.slack_client_secret,
    },
    "jira": {
        "authorize_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        # Atlassian Cloud 3LO scopes. offline_access enables refresh tokens;
        # manage:jira-webhook lets the connector register/delete webhooks.
        "scopes": "read:jira-work read:jira-user manage:jira-webhook offline_access",
        "client_id": lambda: settings.jira_client_id,
        "client_secret": lambda: settings.jira_client_secret,
    },
}

SOURCE_MAP = {
    "linear": SourceType.LINEAR,
    "github": SourceType.GITHUB,
    "slack": SourceType.SLACK,
    "jira": SourceType.JIRA,
}

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0"}


def _resolve_frontend_base(request: Request) -> str:
    """Public base URL of the frontend, used to build OAuth redirect URIs.

    Honors X-Forwarded-Proto/Host so the redirect matches the domain the
    user is actually on, regardless of FRONTEND_URL. Falls back to
    settings.frontend_url only when the backend was reached over loopback,
    which is the local-dev case where the frontend lives on a different port.
    """
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    hostname = host.split(":")[0].lower()
    if hostname in _LOOPBACK_HOSTS and settings.frontend_url:
        return settings.frontend_url.rstrip("/")
    return f"{scheme}://{host}"


def _build_oauth_redirect_uri(request: Request, connector: str) -> str:
    return f"{_resolve_frontend_base(request)}/connections/{connector}/callback"


@router.get(
    "/{connector}/connect",
    response_model=OAuthConnectResponse,
    summary="Start OAuth flow",
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def oauth_connect(
    request: Request,
    connector: str,
    org_id: UUID = Query(...),
):
    """Redirect user to OAuth authorization URL."""
    if connector not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    config = OAUTH_CONFIG[connector]
    client_id = config["client_id"]()
    if not client_id:
        raise HTTPException(status_code=500, detail=f"{connector} OAuth not configured")

    state = f"{org_id}:{secrets.token_urlsafe(16)}"
    redirect_uri = _build_oauth_redirect_uri(request, connector)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": config["scopes"],
        "state": state,
        "response_type": "code",
    }

    if connector == "slack":
        # Slack supports both bot scopes (scope=) and user scopes (user_scope=).
        # We request both so we can read with the user token AND post DMs with the bot token.
        params["user_scope"] = config.get("user_scopes", "")
    elif connector == "jira":
        # Atlassian Cloud 3LO requires audience and recommends prompt=consent
        # so users always see the scope screen.
        params["audience"] = "api.atlassian.com"
        params["prompt"] = "consent"

    authorize_url = f"{config['authorize_url']}?{urlencode(params)}"

    return {"redirect_url": authorize_url}


@router.get(
    "/{connector}/callback",
    response_model=OAuthCallbackResponse,
    summary="OAuth callback",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        502: {"model": ErrorResponse},
    },
)
async def oauth_callback(
    request: Request,
    connector: str,
    code: str = Query(...),
    state: str = Query(""),
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback - exchange code for tokens."""
    if connector not in OAUTH_CONFIG:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    # Extract org_id from state
    org_id_str = state.split(":")[0] if ":" in state else None
    if not org_id_str:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    try:
        org_id = UUID(org_id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid org_id in state")

    # Verify org exists
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    config = OAUTH_CONFIG[connector]
    redirect_uri = _build_oauth_redirect_uri(request, connector)

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_data = {
            "client_id": config["client_id"](),
            "client_secret": config["client_secret"](),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        headers = {"Accept": "application/json"}
        resp = await client.post(config["token_url"], data=token_data, headers=headers)

        if resp.status_code != 200:
            logger.error("OAuth token exchange failed for %s (status=%s)", connector, resp.status_code)
            raise HTTPException(status_code=502, detail="Token exchange failed")

        token_resp = resp.json()

    # Extract workspace identifier for multi-org webhook routing
    workspace_id: str | None = None
    if connector == "slack":
        workspace_id = token_resp.get("team", {}).get("id")
    elif connector == "linear":
        # Fetch Linear organization ID via GraphQL
        linear_access_token = token_resp.get("access_token", "")
        if linear_access_token:
            try:
                async with httpx.AsyncClient() as gql_client:
                    gql_resp = await gql_client.post(
                        "https://api.linear.app/graphql",
                        json={"query": "{ organization { id } }"},
                        headers={"Authorization": linear_access_token},
                    )
                    if gql_resp.status_code == 200:
                        gql_data = gql_resp.json()
                        workspace_id = gql_data.get("data", {}).get("organization", {}).get("id")
            except Exception:
                logger.warning("Failed to fetch Linear organization ID")
    elif connector == "github":
        # GitHub uses selected_repos in settings for webhook routing - no workspace_id needed
        pass
    elif connector == "jira":
        # Atlassian Cloud requires looking up the cloud ID via /accessible-resources
        # before any subsequent API calls. We persist it in settings for routing.
        jira_access_token = token_resp.get("access_token", "")
        if jira_access_token:
            try:
                async with httpx.AsyncClient() as ar_client:
                    ar_resp = await ar_client.get(
                        "https://api.atlassian.com/oauth/token/accessible-resources",
                        headers={
                            "Authorization": f"Bearer {jira_access_token}",
                            "Accept": "application/json",
                        },
                    )
                    if ar_resp.status_code == 200:
                        resources = ar_resp.json() or []
                        if resources:
                            workspace_id = resources[0].get("id")
            except Exception:
                logger.warning("Failed to fetch Jira accessible resources")

    # Extract tokens based on connector
    extra_settings: dict = {}
    if connector == "slack":
        # Slack returns both a bot token (top-level access_token, xoxb-) and a user
        # token (authed_user.access_token, xoxp-). We use the bot token for outbound
        # posting (DMs for briefings) and inbound API calls, and persist the user
        # token in settings for any future user-context calls.
        access_token = token_resp.get("access_token", "")
        user_access_token = token_resp.get("authed_user", {}).get("access_token", "")
        if user_access_token:
            extra_settings["user_token"] = user_access_token
        refresh_token = None
    else:
        access_token = token_resp.get("access_token", "")
        refresh_token = token_resp.get("refresh_token")

    if not access_token:
        raise HTTPException(status_code=502, detail="No access token in response")

    # Upsert OAuthToken
    source = SOURCE_MAP[connector]
    existing = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token_row = existing.scalar_one_or_none()

    if token_row:
        token_row.access_token = access_token
        token_row.refresh_token = refresh_token
        token_row.scopes = config["scopes"]
        token_row.updated_at = datetime.now(timezone.utc)
        merged_settings = dict(token_row.settings or {})
        if workspace_id:
            merged_settings["workspace_id"] = workspace_id
        merged_settings.update(extra_settings)
        if merged_settings != (token_row.settings or {}):
            token_row.settings = merged_settings
    else:
        token_settings: dict = {}
        if workspace_id:
            token_settings["workspace_id"] = workspace_id
        token_settings.update(extra_settings)
        token_row = OAuthToken(
            org_id=org_id,
            connector=source,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=config["scopes"],
            settings=token_settings,
        )
        db.add(token_row)

    await log_action_safely(
        db,
        org_id=org_id,
        action="connector.connected",
        resource_type="connector",
        details={"connector": connector},
    )
    await db.commit()
    logger.info(f"OAuth token saved for {connector} in org {org_id}")

    await track_connector_connected(
        member_id="system",
        org_id=str(org_id),
        connector=connector,
        scopes=list(config.get("scopes") or []),
    )

    # Redirect to frontend connections page
    return {"status": "connected", "connector": connector, "org_id": str(org_id)}


@router.delete(
    "/{connector}/disconnect",
    response_model=OAuthDisconnectResponse,
    summary="Disconnect connector",
    responses={400: {"model": ErrorResponse}},
)
async def oauth_disconnect(
    connector: str,
    org_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Remove OAuth token for a connector."""
    if connector not in SOURCE_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    source = SOURCE_MAP[connector]
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token_row = result.scalar_one_or_none()
    if token_row:
        await db.delete(token_row)
        await db.commit()

    return {"status": "disconnected", "connector": connector}
