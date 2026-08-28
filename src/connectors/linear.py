"""Linear connector -- ingests issues, projects, and team members via GraphQL."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors._rate_limit import RateLimiter
from src.connectors.base import BaseConnector
from src.connectors.schemas.linear import (
    LinearIssueProperties,
    LinearProjectProperties,
    LinearUserProperties,
)
from src.graph import (
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

GRAPHQL_URL = "https://api.linear.app/graphql"

_LIMITER = RateLimiter(
    requests_per_second=10.0,  # Linear allows ~25 req/min sustained; conservative
    max_retries=4,
    name="linear",
)

# ── GraphQL fragments / queries ──────────────────────────────────────

_ISSUES_QUERY = """
query Issues($after: String, $filter: IssueFilter) {
  issues(first: 100, after: $after, filter: $filter) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      identifier
      title
      description
      priority
      state { id name type }
      assignee { id name email }
      team { id name key }
      project { id name }
      labels { nodes { id name } }
      relations {
        nodes { id type relatedIssue { id identifier } }
      }
      createdAt
      updatedAt
    }
  }
}
"""

_TEAM_MEMBERS_QUERY = """
query TeamMembers($after: String) {
  users(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      name
      email
      displayName
      avatarUrl
      active
    }
  }
}
"""

_PROJECTS_QUERY = """
query Projects($after: String) {
  projects(first: 100, after: $after) {
    pageInfo { hasNextPage endCursor }
    nodes {
      id
      name
      description
      state
      startDate
      targetDate
      lead { id name }
      teams { nodes { id name } }
    }
  }
}
"""


class LinearConnector(BaseConnector):
    source = SourceType.LINEAR

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
                persons = await self._sync_team_members(client, db, org_id, result)
                projects = await self._sync_projects(client, db, org_id, result)
                await self._sync_issues(client, db, org_id, result, persons, projects, issue_filter=None)
        except Exception as exc:
            msg = f"linear full sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
        logger.info(
            "linear full sync org=%s entities=%d/%d edges=%d/%d errors=%d",
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
        since_iso = since.isoformat()
        issue_filter = {"updatedAt": {"gte": since_iso}}

        async with self._make_http_client(token) as client:
            persons = await self._sync_team_members(client, db, org_id, result)
            projects = await self._sync_projects(client, db, org_id, result)
            await self._sync_issues(client, db, org_id, result, persons, projects, issue_filter=issue_filter)
        logger.info(
            "linear delta sync org=%s since=%s entities=%d/%d edges=%d/%d",
            org_id,
            since_iso,
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
        action = payload.get("action")  # "create", "update", "remove"
        event_type = payload.get("type")  # "Issue", "Comment", ...
        data = payload.get("data", {})

        try:
            if event_type == "Issue":
                await self._handle_issue_event(db, org_id, action, data, result)
            elif event_type == "Comment":
                await self._handle_comment_event(db, org_id, action, data, result)
            else:
                logger.debug("linear webhook: ignoring type=%s action=%s", event_type, action)
        except Exception as exc:
            msg = f"linear webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        # Caller (receive_webhook) commits and emits SyncCompleted.
        return result

    # ── internal sync helpers ─────────────────────────────────────────

    async def _sync_team_members(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Return mapping of linear user id -> entity UUID."""
        person_map: dict[str, UUID] = {}
        cursor: str | None = None

        while True:
            variables: dict = {"after": cursor} if cursor else {}
            data = await self._execute_graphql(client, _TEAM_MEMBERS_QUERY, variables)
            users_data = data.get("users", {})
            nodes = users_data.get("nodes", [])

            for user in nodes:
                # Build source_ids with email for cross-source resolution
                person_source_ids: dict[str, str] = {"linear": user["id"]}
                if user.get("email"):
                    person_source_ids["email"] = user["email"].lower()

                entity = await resolve_or_create_person(
                    db,
                    org_id=org_id,
                    source=SourceType.LINEAR,
                    source_ids=person_source_ids,
                    canonical_name=user.get("name") or user.get("displayName", ""),
                    properties=LinearUserProperties(
                        email=user.get("email"),
                        display_name=user.get("displayName"),
                        avatar_url=user.get("avatarUrl"),
                        active=user.get("active", True),
                    ).model_dump(exclude_none=True),
                )
                was_new = entity.created_at == entity.updated_at
                if was_new:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1
                person_map[user["id"]] = entity.id

            page_info = users_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info["endCursor"]
            else:
                break

        return person_map

    async def _sync_projects(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Return mapping of linear project id -> entity UUID."""
        project_map: dict[str, UUID] = {}
        cursor: str | None = None

        while True:
            variables: dict = {"after": cursor} if cursor else {}
            data = await self._execute_graphql(client, _PROJECTS_QUERY, variables)
            projects_data = data.get("projects", {})
            nodes = projects_data.get("nodes", [])

            for proj in nodes:
                entity = await upsert_entity(
                    db,
                    EntityCreate(
                        org_id=org_id,
                        type=EntityType.FEATURE,
                        source=SourceType.LINEAR,
                        source_ids={"linear": proj["id"]},
                        canonical_name=proj["name"],
                        properties=LinearProjectProperties(
                            name=proj["name"],
                            description=proj.get("description"),
                            state=proj.get("state"),
                            start_date=proj.get("startDate"),
                            target_date=proj.get("targetDate"),
                            lead_id=(proj.get("lead") or {}).get("id"),
                            lead_name=(proj.get("lead") or {}).get("name"),
                        ).model_dump(exclude_none=True),
                    ),
                )
                was_new = entity.created_at == entity.updated_at
                if was_new:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1
                project_map[proj["id"]] = entity.id

            page_info = projects_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info["endCursor"]
            else:
                break

        return project_map

    async def _sync_issues(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
        person_map: dict[str, UUID],
        project_map: dict[str, UUID],
        issue_filter: dict | None,
    ) -> None:
        cursor: str | None = None

        while True:
            variables: dict = {}
            if cursor:
                variables["after"] = cursor
            if issue_filter:
                variables["filter"] = issue_filter

            data = await self._execute_graphql(client, _ISSUES_QUERY, variables)
            issues_data = data.get("issues", {})
            nodes = issues_data.get("nodes", [])

            for issue in nodes:
                state_obj = issue.get("state") or {}
                team_obj = issue.get("team") or {}
                assignee_obj = issue.get("assignee") or {}
                task_entity = await resolve_or_create_entity(
                    db,
                    EntityCreate(
                        org_id=org_id,
                        type=EntityType.TASK,
                        source=SourceType.LINEAR,
                        source_ids={
                            "linear": issue["id"],
                            "linear_identifier": issue["identifier"],
                        },
                        canonical_name=f"{issue['identifier']}: {issue['title']}",
                        properties=LinearIssueProperties(
                            identifier=issue["identifier"],
                            title=issue["title"],
                            description=issue.get("description"),
                            priority=issue.get("priority"),
                            state_name=state_obj.get("name"),
                            state_type=state_obj.get("type"),
                            state=state_obj.get("name"),
                            assignee_email=assignee_obj.get("email"),
                            assignee_name=assignee_obj.get("name"),
                            team_key=team_obj.get("key"),
                            team_name=team_obj.get("name"),
                            labels=[lbl["name"] for lbl in (issue.get("labels") or {}).get("nodes", [])],
                            created_at=issue.get("createdAt"),
                            updated_at=issue.get("updatedAt"),
                        ).model_dump(exclude_none=True),
                    ),
                )
                was_new = task_entity.created_at == task_entity.updated_at
                if was_new:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1

                # OWNS edge: assignee -> issue
                assignee = issue.get("assignee")
                if assignee and assignee["id"] in person_map:
                    edge = await upsert_edge(
                        db,
                        EdgeCreate(
                            org_id=org_id,
                            from_entity_id=person_map[assignee["id"]],
                            to_entity_id=task_entity.id,
                            type=EdgeType.OWNS,
                            evidence=[
                                {
                                    "source": "linear",
                                    "field": "assignee",
                                    "issue": issue["identifier"],
                                }
                            ],
                        ),
                    )
                    track_edge_result(edge, result)

                # TAGGED_TO edge: issue -> project
                project = issue.get("project")
                if project and project["id"] in project_map:
                    edge = await upsert_edge(
                        db,
                        EdgeCreate(
                            org_id=org_id,
                            from_entity_id=task_entity.id,
                            to_entity_id=project_map[project["id"]],
                            type=EdgeType.TAGGED_TO,
                            evidence=[
                                {
                                    "source": "linear",
                                    "field": "project",
                                    "issue": issue["identifier"],
                                    "project": project["name"],
                                }
                            ],
                        ),
                    )
                    track_edge_result(edge, result)

                # BLOCKS edges from issue relations
                for relation in (issue.get("relations") or {}).get("nodes", []):
                    if relation.get("type") != "blocks":
                        continue
                    related = relation.get("relatedIssue", {})
                    related_id = related.get("id")
                    if not related_id:
                        continue
                    # Find or create a stub for the related issue
                    related_stub_sids = {"linear": related_id}
                    related_identifier = related.get("identifier")
                    if related_identifier:
                        related_stub_sids["linear_identifier"] = related_identifier
                    related_entity = await resolve_or_create_entity(
                        db,
                        EntityCreate(
                            org_id=org_id,
                            type=EntityType.TASK,
                            source=SourceType.LINEAR,
                            source_ids=related_stub_sids,
                            canonical_name=related_identifier or related_id,
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
                                    "source": "linear",
                                    "relation": "blocks",
                                    "from": issue["identifier"],
                                    "to": related.get("identifier"),
                                }
                            ],
                        ),
                    )
                    track_edge_result(edge, result)

            page_info = issues_data.get("pageInfo", {})
            if page_info.get("hasNextPage"):
                cursor = page_info["endCursor"]
            else:
                break

    # ── webhook event handlers ────────────────────────────────────────

    async def _handle_issue_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        action: str | None,
        data: dict,
        result: ConnectorSyncResult,
    ) -> None:
        if action in ("create", "update"):
            state_raw = data.get("state")
            state_name = state_raw.get("name") if isinstance(state_raw, dict) else state_raw
            state_type = state_raw.get("type") if isinstance(state_raw, dict) else None
            entity_source_ids: dict[str, str] = {"linear": data["id"]}
            identifier = data.get("identifier")
            if identifier:
                entity_source_ids["linear_identifier"] = identifier
            entity = await resolve_or_create_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.TASK,
                    source=SourceType.LINEAR,
                    source_ids=entity_source_ids,
                    canonical_name=f"{data.get('identifier', '')}: {data.get('title', '')}",
                    properties=LinearIssueProperties(
                        identifier=data.get("identifier", ""),
                        title=data.get("title", ""),
                        priority=data.get("priority"),
                        state_name=state_name,
                        state_type=state_type,
                        state=state_name,
                    ).model_dump(exclude_none=True),
                ),
            )
            was_new = entity.created_at == entity.updated_at
            if was_new:
                result.entities_created += 1
            else:
                result.entities_updated += 1

            # Re-link assignee if present
            assignee_id = data.get("assigneeId") or (data.get("assignee") or {}).get("id")
            if assignee_id:
                from src.graph import get_entity_by_source

                person = await get_entity_by_source(db, org_id, SourceType.LINEAR, assignee_id)
                if person:
                    edge = await upsert_edge(
                        db,
                        EdgeCreate(
                            org_id=org_id,
                            from_entity_id=person.id,
                            to_entity_id=entity.id,
                            type=EdgeType.OWNS,
                            evidence=[{"source": "linear_webhook", "action": action}],
                        ),
                    )
                    track_edge_result(edge, result)

    async def _handle_comment_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        action: str | None,
        data: dict,
        result: ConnectorSyncResult,
    ) -> None:
        """Comments are stored as evidence on the parent issue entity."""
        issue_id = data.get("issueId") or (data.get("issue") or {}).get("id")
        if not issue_id:
            return

        from src.graph import get_entity_by_source

        issue_entity = await get_entity_by_source(db, org_id, SourceType.LINEAR, issue_id)
        if not issue_entity:
            logger.warning("linear webhook comment: issue entity not found for %s", issue_id)
            return

        # Append comment metadata to properties
        comments = list(issue_entity.properties.get("recent_comments", []))
        comments.append(
            {
                "comment_id": data.get("id"),
                "user_id": data.get("userId"),
                "body_snippet": (data.get("body") or "")[:200],
                "created_at": data.get("createdAt"),
            }
        )
        # Keep last 20 comments
        issue_entity.properties = {**issue_entity.properties, "recent_comments": comments[-20:]}
        result.entities_updated += 1

    # ── GraphQL helper ────────────────────────────────────────────────

    @staticmethod
    async def _execute_graphql(
        client: httpx.AsyncClient,
        query: str,
        variables: dict | None = None,
    ) -> dict:
        """Execute a GraphQL query against the Linear API and return the ``data`` dict."""
        payload: dict = {"query": query}
        if variables:
            payload["variables"] = variables

        body = await _LIMITER.request_json(
            client,
            "POST",
            GRAPHQL_URL,
            json=payload,
            retry_on_status={429, 503},
        )

        if "errors" in body:
            error_msgs = [e.get("message", str(e)) for e in body["errors"]]
            logger.error("linear graphql errors: %s", error_msgs)
            raise RuntimeError(f"Linear GraphQL errors: {error_msgs}")

        return body.get("data", {})
