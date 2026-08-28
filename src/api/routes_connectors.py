"""Connector status, settings, sync, and webhook routes."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db, verify_webhook_signature
from src.api.rate_limit import limiter
from src.api.rbac import ADMIN_ROLES, require_role
from src.api.schemas import (
    ConnectorListResponse,
    ConnectorSettingsResponse,
    ConnectorSettingsUpdateRequest,
    ConnectorStatusResponse,
    GitHubRepoListResponse,
    GitHubRepoResponse,
    SyncTriggerResponse,
)
from src.connectors.registry import (
    CONNECTORS,
    get_connector,
    source_for_slug,
    spec_for_slug,
)
from src.shared.audit import log_action_safely
from src.shared.models import OAuthToken, OrgMember, SyncState
from src.shared.types import SourceType, SyncStatus
from src.shared.webhook_secrets import github_webhook_secret

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["connectors"])


# ── Connector status ───────────────────────────────────────────────────


@router.get("/orgs/{org_id}/connectors", response_model=ConnectorListResponse)
async def get_connector_status(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    # Only connectors with an implementation in src/connectors/. Observability
    # and analytics sources are on the roadmap but have no sync yet, and
    # advertising them here made the product look like it had them.
    v1_connectors = [spec.source for spec in CONNECTORS]

    tokens_result = await db.execute(select(OAuthToken).where(OAuthToken.org_id == org_id))
    tokens = {t.connector: t for t in tokens_result.scalars().all()}

    syncs_result = await db.execute(select(SyncState).where(SyncState.org_id == org_id))
    syncs = {s.connector: s for s in syncs_result.scalars().all()}

    connectors = []
    for source in v1_connectors:
        sync = syncs.get(source)
        token = tokens.get(source)
        connectors.append(
            ConnectorStatusResponse(
                connector=source,
                connected=token is not None,
                last_sync_at=sync.last_sync_at if sync else None,
                status=sync.status if sync else SyncStatus.IDLE,
                error_message=sync.error_message if sync else None,
                needs_reauth=_token_needs_reauth(source, token),
            )
        )

    return ConnectorListResponse(items=connectors)


def _token_needs_reauth(source: SourceType, token: OAuthToken | None) -> bool:
    """Return True if the stored token is missing scopes required for newer features."""
    if token is None:
        return False
    granted = {s.strip() for s in (token.scopes or "").split(",") if s.strip()}
    if source == SourceType.SLACK:
        # Briefing DMs require chat:write and im:write -- tokens issued before
        # this scope split won't have them.
        return not {"chat:write", "im:write"}.issubset(granted)
    return False


@router.get("/orgs/{org_id}/connectors/github/repos", response_model=GitHubRepoListResponse)
async def list_github_repos(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List all GitHub repos accessible to the connected token."""
    import httpx

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == SourceType.GITHUB,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="GitHub not connected")

    selected = set((token.settings or {}).get("selected_repos", []))

    repos: list[GitHubRepoResponse] = []
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
        timeout=httpx.Timeout(30.0, connect=10.0),
    ) as client:
        next_url: str | None = "https://api.github.com/user/repos"
        params: dict[str, str] | None = {"per_page": "100", "sort": "updated"}

        while next_url:
            resp = await client.get(next_url, params=params)
            resp.raise_for_status()
            for r in resp.json():
                repos.append(
                    GitHubRepoResponse(
                        full_name=r["full_name"],
                        name=r["name"],
                        owner=r.get("owner", {}).get("login", ""),
                        private=r.get("private", False),
                        description=r.get("description"),
                        enabled=r["full_name"] in selected,
                    )
                )
            # Follow pagination
            params = None
            next_url = None
            link_header = resp.headers.get("link", "")
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    start = part.index("<") + 1
                    end = part.index(">")
                    next_url = part[start:end]
                    break

    return GitHubRepoListResponse(repos=repos)


@router.put("/orgs/{org_id}/connectors/{connector}/settings", response_model=ConnectorSettingsResponse)
async def update_connector_settings(
    req: ConnectorSettingsUpdateRequest,
    org_id: UUID = Path(...),
    connector: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*ADMIN_ROLES)),
):
    """Update connector settings (selected repos). Manages webhooks for GitHub."""
    import httpx

    from src.connectors.github import GitHubConnector

    source = source_for_slug(connector)
    if not source:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail=f"{connector} not connected")

    old_settings = token.settings or {}
    old_selected = set(old_settings.get("selected_repos", []))
    new_selected = set(req.selected_repos)
    webhook_ids: dict[str, int] = dict(old_settings.get("webhook_ids", {}))

    # Manage GitHub webhooks for added/removed repos
    if connector == "github":
        from src.config import settings

        webhook_url = f"{settings.app_url}/api/webhooks/github"
        webhook_secret = github_webhook_secret(settings)

        added = new_selected - old_selected
        removed = old_selected - new_selected

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            # Create webhooks for newly enabled repos
            for repo in added:
                try:
                    hook_id = await GitHubConnector.create_repo_webhook(
                        client,
                        repo,
                        webhook_url,
                        webhook_secret,
                    )
                    webhook_ids[repo] = hook_id
                    logger.info("Created webhook for %s (hook_id=%d)", repo, hook_id)
                except Exception as exc:
                    logger.warning("Failed to create webhook for %s: %s", repo, exc)

            # Delete webhooks for disabled repos
            for repo in removed:
                hook_id = webhook_ids.pop(repo, None)
                if hook_id:
                    try:
                        await GitHubConnector.delete_repo_webhook(client, repo, hook_id)
                        logger.info("Deleted webhook for %s (hook_id=%d)", repo, hook_id)
                    except Exception as exc:
                        logger.warning("Failed to delete webhook for %s: %s", repo, exc)

    token.settings = {
        **old_settings,
        "selected_repos": list(new_selected),
        "webhook_ids": webhook_ids,
    }
    await db.commit()

    return ConnectorSettingsResponse(
        selected_repos=list(new_selected),
        webhook_ids=webhook_ids,
    )


@router.post("/orgs/{org_id}/connectors/{connector}/sync", response_model=SyncTriggerResponse)
async def trigger_connector_sync(
    org_id: UUID = Path(...),
    connector: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_member: OrgMember = Depends(get_current_member),
):
    """Trigger an immediate sync for a connector."""
    source = source_for_slug(connector)
    if not source:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail=f"{connector} not connected")

    # Get or create sync state
    sync_result = await db.execute(
        select(SyncState).where(
            SyncState.org_id == org_id,
            SyncState.connector == source,
        )
    )
    sync_state = sync_result.scalar_one_or_none()
    if not sync_state:
        sync_state = SyncState(
            org_id=org_id,
            connector=source,
            status=SyncStatus.IDLE,
        )
        db.add(sync_state)
        await db.flush()

    if sync_state.status == SyncStatus.SYNCING:
        # If stuck syncing for more than 10 minutes, assume the previous sync
        # crashed and reset so the user can retry.
        stuck_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
        started_at = sync_state.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        if started_at < stuck_threshold:
            sync_state.status = SyncStatus.IDLE
            sync_state.error_message = "Previous sync timed out - reset automatically"
            await db.flush()
        else:
            raise HTTPException(status_code=409, detail="Sync already in progress")

    try:
        conn = get_connector(source)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"No connector implementation for {connector}"
        ) from None

    since = sync_state.last_sync_at or datetime(2000, 1, 1, tzinfo=timezone.utc)

    sync_state.status = SyncStatus.SYNCING
    sync_state.error_message = None
    await db.flush()

    try:
        result = await conn.sync_delta(db, org_id, token, since=since)
        sync_state.last_sync_at = datetime.now(timezone.utc)
        sync_state.status = SyncStatus.IDLE
        sync_state.error_message = None

        # Emit SyncCompleted - triggers person detection, link suggestions, etc.
        from src.events import SyncCompleted, bus

        await bus.emit(
            SyncCompleted(
                db=db,
                org_id=org_id,
                source=source,
                result=result,
            )
        )

        await log_action_safely(
            db,
            org_id=org_id,
            user_id=current_member.user_id,
            action="connector.synced",
            resource_type="connector",
            details={
                "connector": connector,
                "entities_created": result.entities_created,
                "entities_updated": result.entities_updated,
            },
        )

        await db.commit()

        return SyncTriggerResponse(
            status="ok",
            entities_created=result.entities_created,
            entities_updated=result.entities_updated,
            edges_created=result.edges_created,
            edges_updated=result.edges_updated,
            errors=result.errors[:10],
        )
    except Exception as exc:
        sync_state.status = SyncStatus.ERROR
        sync_state.error_message = str(exc)[:2000]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")


# ── Webhooks ───────────────────────────────────────────────────────────


@router.post("/webhooks/{connector}")
@limiter.limit("120/minute")
async def receive_webhook(
    connector: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_webhook_signature),
):
    """Receive webhook from Linear, GitHub, Slack, or Jira."""
    try:
        payload = await request.json()
        logger.info("Webhook received from %s", connector)

        from src.events import SyncCompleted, bus

        if connector == "slack" and payload.get("type") == "url_verification":
            return {"challenge": payload.get("challenge")}

        spec = spec_for_slug(connector)
        if spec is None or not spec.supports_webhooks:
            return {"status": "ignored"}

        conn = get_connector(spec.source)

        org_id = await _extract_org_from_webhook(db, payload, connector)
        if org_id:
            # Set RLS context for webhook-originated DB queries
            from src.shared.database import set_current_org_id

            set_current_org_id(str(org_id))
            result = await conn.handle_webhook(db, org_id, payload)
            await bus.emit(
                SyncCompleted(db=db, org_id=org_id, source=spec.source, result=result)
            )
            await db.commit()
            return {"status": "processed", "result": result.model_dump()}

    except Exception as e:
        logger.error("Webhook processing failed for %s: %s", connector, e)
        return {"status": "error", "detail": str(e)}

    return {"status": "ignored"}


async def _extract_org_from_webhook(db: AsyncSession, payload: dict, connector: str) -> UUID | None:
    """Extract org_id from webhook payload by matching the repo to a connected token."""
    source = source_for_slug(connector)
    if not source:
        return None

    # GitHub: match repo full_name against an explicit selected_repos entry.
    # No sync-all shortcut: operators must list repos explicitly; otherwise the
    # webhook cannot be attributed to a specific tenant.
    if connector == "github":
        repo_name = (payload.get("repository") or {}).get("full_name")
        if not repo_name:
            return None
        result = await db.execute(select(OAuthToken).where(OAuthToken.connector == source))
        for token in result.scalars().all():
            selected = (token.settings or {}).get("selected_repos", [])
            if selected and repo_name in selected:
                return token.org_id
        return None

    # Linear: match organizationId from webhook payload against stored workspace_id.
    if connector == "linear":
        webhook_ws_id = payload.get("organizationId")
        if not webhook_ws_id:
            return None
        result = await db.execute(select(OAuthToken).where(OAuthToken.connector == source))
        for token in result.scalars().all():
            stored_ws_id = (token.settings or {}).get("workspace_id")
            if stored_ws_id and stored_ws_id == webhook_ws_id:
                return token.org_id
        return None

    # Slack: match team_id from webhook payload against stored workspace_id.
    if connector == "slack":
        webhook_team_id = payload.get("team_id") or payload.get("event", {}).get("team")
        if not webhook_team_id:
            return None
        result = await db.execute(select(OAuthToken).where(OAuthToken.connector == source))
        for token in result.scalars().all():
            stored_ws_id = (token.settings or {}).get("workspace_id")
            if stored_ws_id and stored_ws_id == webhook_team_id:
                return token.org_id
        return None

    # Jira: match cloudId or matchedWebhookIds against the stored cloud_id and webhook_ids.
    if connector == "jira":
        cloud_id = payload.get("cloudId") or payload.get("cloud_id")
        matched_ids = payload.get("matchedWebhookIds") or []
        result = await db.execute(select(OAuthToken).where(OAuthToken.connector == source))
        for token in result.scalars().all():
            settings_dict = token.settings or {}
            stored_cloud = settings_dict.get("workspace_id") or settings_dict.get("cloud_id")
            if cloud_id and stored_cloud and stored_cloud == cloud_id:
                return token.org_id
            stored_webhook_ids = set(settings_dict.get("webhook_ids", []) or [])
            if stored_webhook_ids and any(mid in stored_webhook_ids for mid in matched_ids):
                return token.org_id
        return None

    return None
