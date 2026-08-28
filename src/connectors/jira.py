"""Jira connector -- ingests issues, projects, and users via Atlassian Cloud REST v3."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.connectors.base import BaseConnector
from src.connectors.schemas.jira import (
    JiraIssueProperties,
    JiraProjectProperties,
    JiraUserProperties,
)
from src.graph import (
    get_entity_by_source,
    resolve_or_create_entity,
    resolve_or_create_person,
    track_edge_result,
    upsert_edge,
    upsert_entity,
)
from src.shared.models import OAuthToken
from src.shared.types import (
    ConnectorSyncResult,
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    SourceType,
)

logger = logging.getLogger(__name__)

# Jira ADF descriptions are nested doc trees; we extract plain text up to this length.
_DESCRIPTION_TEXT_LIMIT = 4000


def _adf_to_text(node: dict | str | None) -> str | None:
    """Walk an Atlassian Document Format node and return concatenated plain text."""
    if node is None:
        return None
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return None

    if node.get("type") == "text":
        return node.get("text", "")

    parts: list[str] = []
    for child in node.get("content", []) or []:
        text = _adf_to_text(child)
        if text:
            parts.append(text)
    joined = "".join(parts).strip()
    return joined[:_DESCRIPTION_TEXT_LIMIT] if joined else None


def _cloud_id(token: OAuthToken) -> str | None:
    return (token.settings or {}).get("workspace_id") or (token.settings or {}).get("cloud_id")


def _api_base(token: OAuthToken) -> str:
    cid = _cloud_id(token)
    if not cid:
        raise RuntimeError("Jira token is missing cloud_id; reconnect required")
    return f"https://api.atlassian.com/ex/jira/{cid}/rest/api/3"


class JiraConnector(BaseConnector):
    source = SourceType.JIRA

    # ── public interface ──────────────────────────────────────────────

    async def sync_full(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        try:
            async with self._make_http_client(token) as client:
                base = _api_base(token)
                persons = await self._sync_users(client, base, db, org_id, result)
                projects = await self._sync_projects(client, base, db, org_id, result)
                await self._sync_issues(
                    client, base, db, org_id, result, persons, projects, jql=None
                )
                await self._ensure_webhook_registered(client, base, token, db)
        except Exception as exc:
            msg = f"jira full sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        logger.info(
            "jira full sync org=%s entities=%d/%d edges=%d/%d errors=%d",
            org_id,
            result.entities_created,
            result.entities_updated,
            result.edges_created,
            result.edges_updated,
            len(result.errors),
        )
        return result

    async def sync_delta(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
        since: datetime,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        # JQL needs the timestamp formatted as "yyyy/MM/dd HH:mm".
        since_jql = since.strftime("%Y/%m/%d %H:%M")
        jql = f'updated >= "{since_jql}"'

        try:
            async with self._make_http_client(token) as client:
                base = _api_base(token)
                persons = await self._sync_users(client, base, db, org_id, result)
                projects = await self._sync_projects(client, base, db, org_id, result)
                await self._sync_issues(client, base, db, org_id, result, persons, projects, jql=jql)
        except Exception as exc:
            msg = f"jira delta sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        logger.info(
            "jira delta sync org=%s since=%s entities=%d/%d edges=%d/%d",
            org_id,
            since_jql,
            result.entities_created,
            result.entities_updated,
            result.edges_created,
            result.edges_updated,
        )
        return result

    async def handle_webhook(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        event = payload.get("webhookEvent") or ""

        try:
            if event in ("jira:issue_created", "jira:issue_updated"):
                issue = payload.get("issue")
                if issue:
                    await self._upsert_issue_entity(db, org_id, issue, result, edges=False)
            elif event == "comment_created":
                issue = payload.get("issue")
                comment = payload.get("comment")
                if issue and comment:
                    await self._handle_comment_event(db, org_id, issue, comment, result)
            else:
                logger.debug("jira webhook: ignoring event=%s", event)
        except Exception as exc:
            msg = f"jira webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        return result

    # ── internal: users ───────────────────────────────────────────────

    async def _sync_users(
        self,
        client: httpx.AsyncClient,
        base: str,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Return mapping of jira accountId -> entity UUID."""
        person_map: dict[str, UUID] = {}
        start_at = 0
        page_size = 100

        while True:
            resp = await client.get(
                f"{base}/users/search",
                params={"startAt": start_at, "maxResults": page_size},
            )
            if resp.status_code == 403:
                # Some Atlassian sites restrict /users/search; bail without failing the whole sync.
                logger.warning("jira /users/search returned 403 -- skipping user sync")
                break
            resp.raise_for_status()
            users = resp.json() or []

            for user in users:
                if not user.get("accountId"):
                    continue
                if user.get("accountType") not in (None, "atlassian"):
                    # Skip app/customer accounts - they aren't real org members.
                    continue

                source_ids: dict[str, str] = {"jira": user["accountId"]}
                if user.get("emailAddress"):
                    source_ids["email"] = user["emailAddress"].lower()

                entity = await resolve_or_create_person(
                    db,
                    org_id=org_id,
                    source=SourceType.JIRA,
                    source_ids=source_ids,
                    canonical_name=user.get("displayName") or user.get("emailAddress") or user["accountId"],
                    properties=JiraUserProperties(
                        account_id=user["accountId"],
                        email=user.get("emailAddress"),
                        display_name=user.get("displayName"),
                        avatar_url=(user.get("avatarUrls") or {}).get("48x48"),
                        active=user.get("active", True),
                        account_type=user.get("accountType"),
                    ).model_dump(exclude_none=True),
                )
                if entity.created_at == entity.updated_at:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1
                person_map[user["accountId"]] = entity.id

            if len(users) < page_size:
                break
            start_at += page_size

        return person_map

    # ── internal: projects ────────────────────────────────────────────

    async def _sync_projects(
        self,
        client: httpx.AsyncClient,
        base: str,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Return mapping of jira projectId -> entity UUID."""
        project_map: dict[str, UUID] = {}
        start_at = 0
        page_size = 50

        while True:
            resp = await client.get(
                f"{base}/project/search",
                params={"startAt": start_at, "maxResults": page_size},
            )
            resp.raise_for_status()
            body = resp.json() or {}
            values = body.get("values", [])

            for proj in values:
                lead = proj.get("lead") or {}
                entity = await upsert_entity(
                    db,
                    EntityCreate(
                        org_id=org_id,
                        type=EntityType.FEATURE,
                        source=SourceType.JIRA,
                        source_ids={
                            "jira": proj["id"],
                            "jira_key": proj["key"],
                        },
                        canonical_name=proj.get("name") or proj["key"],
                        properties=JiraProjectProperties(
                            key=proj["key"],
                            name=proj.get("name") or proj["key"],
                            project_type_key=proj.get("projectTypeKey"),
                            description=proj.get("description"),
                            lead_account_id=lead.get("accountId"),
                            lead_name=lead.get("displayName"),
                            url=proj.get("self"),
                        ).model_dump(exclude_none=True),
                    ),
                )
                if entity.created_at == entity.updated_at:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1
                project_map[proj["id"]] = entity.id

            if body.get("isLast", True) or len(values) < page_size:
                break
            start_at += page_size

        return project_map

    # ── internal: issues ──────────────────────────────────────────────

    async def _sync_issues(
        self,
        client: httpx.AsyncClient,
        base: str,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
        person_map: dict[str, UUID],
        project_map: dict[str, UUID],
        jql: str | None,
    ) -> None:
        start_at = 0
        page_size = 100
        fields = ",".join(
            [
                "summary",
                "description",
                "status",
                "priority",
                "issuetype",
                "assignee",
                "reporter",
                "project",
                "labels",
                "components",
                "duedate",
                "parent",
                "issuelinks",
                "created",
                "updated",
            ]
        )

        while True:
            params: dict = {
                "startAt": start_at,
                "maxResults": page_size,
                "fields": fields,
            }
            if jql:
                params["jql"] = jql

            resp = await client.get(f"{base}/search", params=params)
            resp.raise_for_status()
            body = resp.json() or {}
            issues = body.get("issues", [])

            for issue in issues:
                await self._upsert_issue_entity(
                    db,
                    org_id,
                    issue,
                    result,
                    edges=True,
                    person_map=person_map,
                    project_map=project_map,
                )

            total = body.get("total", 0)
            start_at += len(issues)
            if not issues or start_at >= total:
                break

    async def _upsert_issue_entity(
        self,
        db: AsyncSession,
        org_id: UUID,
        issue: dict,
        result: ConnectorSyncResult,
        *,
        edges: bool,
        person_map: dict[str, UUID] | None = None,
        project_map: dict[str, UUID] | None = None,
    ) -> None:
        fields = issue.get("fields", {}) or {}
        status = fields.get("status") or {}
        category = (status.get("statusCategory") or {}).get("key")
        assignee = fields.get("assignee") or {}
        reporter = fields.get("reporter") or {}
        project = fields.get("project") or {}
        priority = (fields.get("priority") or {}).get("name")
        issue_type = (fields.get("issuetype") or {}).get("name")
        components = [c.get("name") for c in (fields.get("components") or []) if c.get("name")]

        canonical = f"{issue['key']}: {fields.get('summary', '')}".strip()
        properties = JiraIssueProperties(
            key=issue["key"],
            summary=fields.get("summary", ""),
            description=_adf_to_text(fields.get("description")),
            issue_type=issue_type,
            priority=priority,
            status_name=status.get("name"),
            status_category=category,
            assignee_email=assignee.get("emailAddress"),
            assignee_name=assignee.get("displayName"),
            reporter_email=reporter.get("emailAddress"),
            reporter_name=reporter.get("displayName"),
            project_key=project.get("key"),
            project_name=project.get("name"),
            labels=fields.get("labels") or [],
            components=components,
            due_date=fields.get("duedate"),
            created_at=fields.get("created"),
            updated_at=fields.get("updated"),
            state=status.get("name"),
        ).model_dump(exclude_none=True)

        task_entity = await resolve_or_create_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.TASK,
                source=SourceType.JIRA,
                source_ids={
                    "jira": issue["id"],
                    "jira_key": issue["key"],
                },
                canonical_name=canonical or issue["key"],
                properties=properties,
            ),
        )
        if task_entity.created_at == task_entity.updated_at:
            result.entities_created += 1
        else:
            result.entities_updated += 1

        if not edges:
            return

        # OWNS edge: assignee -> issue
        assignee_id = assignee.get("accountId") if assignee else None
        if assignee_id:
            person_uid: UUID | None = (person_map or {}).get(assignee_id)
            if person_uid is None:
                # Fall back to a lookup if the user wasn't covered by /users/search.
                person_entity = await get_entity_by_source(db, org_id, SourceType.JIRA, assignee_id)
                if person_entity:
                    person_uid = person_entity.id
            if person_uid:
                edge = await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=person_uid,
                        to_entity_id=task_entity.id,
                        type=EdgeType.OWNS,
                        evidence=[
                            {
                                "source": "jira",
                                "field": "assignee",
                                "issue": issue["key"],
                            }
                        ],
                    ),
                )
                track_edge_result(edge, result)

        # TAGGED_TO edge: issue -> project
        project_id = project.get("id") if project else None
        if project_id:
            project_uid = (project_map or {}).get(project_id)
            if project_uid is None:
                project_entity = await get_entity_by_source(db, org_id, SourceType.JIRA, project_id)
                if project_entity:
                    project_uid = project_entity.id
            if project_uid:
                edge = await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=task_entity.id,
                        to_entity_id=project_uid,
                        type=EdgeType.TAGGED_TO,
                        evidence=[
                            {
                                "source": "jira",
                                "field": "project",
                                "issue": issue["key"],
                                "project": project.get("key"),
                            }
                        ],
                    ),
                )
                track_edge_result(edge, result)

        # CONTAINS edge: parent (epic / story) -> child issue
        parent = fields.get("parent")
        if parent and parent.get("id"):
            parent_entity = await resolve_or_create_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.TASK,
                    source=SourceType.JIRA,
                    source_ids={
                        "jira": parent["id"],
                        "jira_key": parent.get("key", parent["id"]),
                    },
                    canonical_name=parent.get("key") or parent["id"],
                ),
            )
            edge = await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=parent_entity.id,
                    to_entity_id=task_entity.id,
                    type=EdgeType.CONTAINS,
                    evidence=[
                        {
                            "source": "jira",
                            "relation": "parent",
                            "from": parent.get("key"),
                            "to": issue["key"],
                        }
                    ],
                ),
            )
            track_edge_result(edge, result)

        # BLOCKS edges from issuelinks.
        for link in fields.get("issuelinks", []) or []:
            link_type = (link.get("type") or {}).get("name", "").lower()
            if link_type != "blocks":
                continue
            outward = link.get("outwardIssue")  # this issue blocks <outwardIssue>
            if not outward or not outward.get("id"):
                continue
            related_entity = await resolve_or_create_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.TASK,
                    source=SourceType.JIRA,
                    source_ids={
                        "jira": outward["id"],
                        "jira_key": outward.get("key", outward["id"]),
                    },
                    canonical_name=outward.get("key") or outward["id"],
                ),
            )
            edge = await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=task_entity.id,
                    to_entity_id=related_entity.id,
                    type=EdgeType.BLOCKS,
                    evidence=[
                        {
                            "source": "jira",
                            "relation": "blocks",
                            "from": issue["key"],
                            "to": outward.get("key"),
                        }
                    ],
                ),
            )
            track_edge_result(edge, result)

    async def _handle_comment_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        issue: dict,
        comment: dict,
        result: ConnectorSyncResult,
    ) -> None:
        """Append a comment snippet to the parent issue entity's properties."""
        issue_id = issue.get("id")
        if not issue_id:
            return

        issue_entity = await get_entity_by_source(db, org_id, SourceType.JIRA, issue_id)
        if not issue_entity:
            logger.warning("jira webhook comment: issue entity not found for %s", issue_id)
            return

        author = comment.get("author") or {}
        comments = list(issue_entity.properties.get("recent_comments", []))
        comments.append(
            {
                "comment_id": comment.get("id"),
                "user_id": author.get("accountId"),
                "user_name": author.get("displayName"),
                "body_snippet": (_adf_to_text(comment.get("body")) or "")[:200],
                "created_at": comment.get("created"),
            }
        )
        issue_entity.properties = {**issue_entity.properties, "recent_comments": comments[-20:]}
        result.entities_updated += 1

    # ── webhook registration ──────────────────────────────────────────

    async def _ensure_webhook_registered(
        self,
        client: httpx.AsyncClient,
        base: str,
        token: OAuthToken,
        db: AsyncSession,
    ) -> None:
        """Register a webhook with Atlassian if we don't have one yet for this token.

        Stores returned webhook IDs in OAuthToken.settings['webhook_ids'] for cleanup.
        Failures are logged but don't fail the sync; the connector still works
        without webhooks (just no real-time updates).
        """
        existing = (token.settings or {}).get("webhook_ids") or []
        if existing:
            return

        app_url = (settings.app_url or "").rstrip("/") if hasattr(settings, "app_url") else ""
        if not app_url:
            logger.info("Skipping Jira webhook registration: app_url not set")
            return

        secret = settings.jira_signing_secret
        if not secret:
            logger.info("Skipping Jira webhook registration: JIRA_SIGNING_SECRET not set")
            return

        webhook_url = f"{app_url}/api/webhooks/jira?secret={secret}"
        body = {
            "url": webhook_url,
            "webhooks": [
                {
                    "events": [
                        "jira:issue_created",
                        "jira:issue_updated",
                        "comment_created",
                    ],
                    "jqlFilter": "project is not empty",
                }
            ],
        }
        try:
            resp = await client.post(f"{base}/webhook", json=body)
            if resp.status_code in (200, 201):
                payload = resp.json() or {}
                registrations = payload.get("webhookRegistrationResult", []) or []
                ids = [
                    w.get("createdWebhookId")
                    for w in registrations
                    if w.get("createdWebhookId")
                ]
                if ids:
                    new_settings = dict(token.settings or {})
                    new_settings["webhook_ids"] = ids
                    token.settings = new_settings
                    logger.info("Registered jira webhooks ids=%s", ids)
            else:
                logger.warning(
                    "jira webhook registration failed status=%s body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
        except Exception:
            logger.warning("jira webhook registration raised", exc_info=True)
