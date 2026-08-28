"""GitHub connector -- ingests repos, PRs, deployments, and contributors via REST API."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, AsyncIterator
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors.base import BaseConnector
from src.connectors.schemas.github import (
    GitHubContributorProperties,
    GitHubDeploymentProperties,
    GitHubPRProperties,
)
from src.graph import (
    get_entity_by_source,
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

API_BASE = "https://api.github.com"


class GitHubConnector(BaseConnector):
    source = SourceType.GITHUB

    # ── repo filtering ───────────────────────────────────────────────

    @staticmethod
    def _get_selected_repos(token: OAuthToken) -> set[str] | None:
        """Return set of selected repo full_names, or None for 'sync all'."""
        selected = (token.settings or {}).get("selected_repos", [])
        return set(selected) if selected else None

    # ── webhook management ───────────────────────────────────────────

    @staticmethod
    async def create_repo_webhook(
        client: httpx.AsyncClient,
        repo_full_name: str,
        webhook_url: str,
        secret: str,
    ) -> int:
        """Create a webhook on a GitHub repo. Returns the hook ID."""
        resp = await client.post(
            f"{API_BASE}/repos/{repo_full_name}/hooks",
            json={
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": secret,
                },
                "events": ["pull_request", "push", "deployment_status"],
                "active": True,
            },
        )
        resp.raise_for_status()
        return resp.json()["id"]

    @staticmethod
    async def delete_repo_webhook(
        client: httpx.AsyncClient,
        repo_full_name: str,
        hook_id: int,
    ) -> None:
        """Delete a webhook from a GitHub repo."""
        resp = await client.delete(
            f"{API_BASE}/repos/{repo_full_name}/hooks/{hook_id}",
        )
        # 404 means already deleted - that's fine
        if resp.status_code != 404:
            resp.raise_for_status()

    # ── public interface ──────────────────────────────────────────────

    async def sync_full(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        selected = self._get_selected_repos(token)

        try:
            async with self._make_http_client(token) as client:
                synced_repo_names: set[str] = set()

                orgs = await self._get_user_orgs(client)
                for gh_org in orgs:
                    org_login = gh_org["login"]
                    repos = await self._get_org_repos(client, org_login)

                    for repo in repos:
                        if selected is not None and repo["full_name"] not in selected:
                            continue
                        await self._sync_repo(client, db, org_id, repo, result, since=None)
                        synced_repo_names.add(repo["full_name"])

                # Also sync user-owned / collaborator repos not covered by org repos
                user_repos = await self._get_user_repos(client)
                for repo in user_repos:
                    if selected is not None and repo["full_name"] not in selected:
                        continue
                    if repo["full_name"] in synced_repo_names:
                        continue
                    await self._sync_repo(client, db, org_id, repo, result, since=None)
        except Exception as exc:
            msg = f"github full sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        logger.info(
            "github full sync org=%s entities=%d/%d edges=%d/%d errors=%d",
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
        selected = self._get_selected_repos(token)

        async with self._make_http_client(token) as client:
            synced_repo_names: set[str] = set()

            orgs = await self._get_user_orgs(client)
            for gh_org in orgs:
                org_login = gh_org["login"]
                repos = await self._get_org_repos(client, org_login)

                for repo in repos:
                    if selected is not None and repo["full_name"] not in selected:
                        continue
                    await self._sync_repo(client, db, org_id, repo, result, since=since)
                    synced_repo_names.add(repo["full_name"])

            # Also sync user-owned / collaborator repos not covered by org repos
            user_repos = await self._get_user_repos(client)
            for repo in user_repos:
                if selected is not None and repo["full_name"] not in selected:
                    continue
                if repo["full_name"] in synced_repo_names:
                    continue
                await self._sync_repo(client, db, org_id, repo, result, since=since)

        logger.info(
            "github delta sync org=%s since=%s entities=%d/%d edges=%d/%d",
            org_id,
            since.isoformat(),
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
        event = payload.get("action", "")
        try:
            if "pull_request" in payload:
                await self._handle_pr_event(db, org_id, payload, result)
            elif "deployment_status" in payload:
                await self._handle_deployment_status_event(db, org_id, payload, result)
            elif "commits" in payload:
                # push event
                await self._handle_push_event(db, org_id, payload, result)
            else:
                logger.debug("github webhook: unhandled event action=%s", event)
        except Exception as exc:
            msg = f"github webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        # Caller (receive_webhook) commits and emits SyncCompleted.
        return result

    # ── internal: repo-level sync ─────────────────────────────────────

    async def _sync_repo(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        repo: dict,
        result: ConnectorSyncResult,
        since: datetime | None,
    ) -> None:
        full_name = repo["full_name"]  # e.g. "myorg/myrepo"

        # Contributors
        person_map = await self._sync_contributors(client, db, org_id, full_name, result)

        # Pull requests
        await self._sync_pull_requests(client, db, org_id, full_name, result, person_map, since)

        # Deployments
        await self._sync_deployments(client, db, org_id, full_name, result, since)

    async def _sync_contributors(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        repo_full_name: str,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Return mapping of GitHub login -> entity UUID."""
        person_map: dict[str, UUID] = {}
        url = f"{API_BASE}/repos/{repo_full_name}/contributors"

        async for contributor in self._paginate(client, url, params={"per_page": "100"}):
            login = contributor.get("login", "")
            if contributor.get("type") != "User":
                continue

            entity = await resolve_or_create_person(
                db,
                org_id=org_id,
                source=SourceType.GITHUB,
                source_ids={
                    "github": login,
                    "github_id": str(contributor.get("id", "")),
                },
                canonical_name=login,
                properties=GitHubContributorProperties(
                    login=login,
                    avatar_url=contributor.get("avatar_url"),
                    contributions=contributor.get("contributions", 0),
                    html_url=contributor.get("html_url"),
                ).model_dump(exclude_none=True),
            )
            was_new = entity.created_at == entity.updated_at
            if was_new:
                result.entities_created += 1
            else:
                result.entities_updated += 1
            person_map[login] = entity.id

        return person_map

    async def _sync_pull_requests(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        repo_full_name: str,
        result: ConnectorSyncResult,
        person_map: dict[str, UUID],
        since: datetime | None,
    ) -> None:
        url = f"{API_BASE}/repos/{repo_full_name}/pulls"
        params: dict[str, str] = {
            "state": "all",
            "sort": "updated",
            "direction": "desc",
            "per_page": "100",
        }
        if since:
            params["since"] = since.isoformat()

        async for pr in self._paginate(client, url, params=params):
            pr_number = pr["number"]
            source_id = f"{repo_full_name}#{pr_number}"

            pr_entity = await upsert_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.COMMIT_PR,
                    source=SourceType.GITHUB,
                    source_ids={"github": source_id},
                    canonical_name=f"PR #{pr_number}: {pr['title']}",
                    properties=GitHubPRProperties(
                        repo=repo_full_name,
                        number=pr_number,
                        title=pr["title"],
                        body=pr.get("body"),
                        state=pr["state"],
                        draft=pr.get("draft", False),
                        merged=pr.get("merged", False) or bool(pr.get("merged_at")),
                        merged_at=pr.get("merged_at"),
                        head_branch=pr.get("head", {}).get("ref"),
                        base_branch=pr.get("base", {}).get("ref"),
                        additions=pr.get("additions"),
                        deletions=pr.get("deletions"),
                        changed_files=pr.get("changed_files"),
                        author=(pr.get("user") or {}).get("login"),
                        review_state=await self._get_pr_review_state(client, repo_full_name, pr_number),
                        requested_reviewers=[
                            r.get("login") for r in (pr.get("requested_reviewers") or []) if r.get("login")
                        ]
                        or None,
                        commit_messages=await self._get_pr_commit_messages(
                            client,
                            repo_full_name,
                            pr_number,
                        ),
                        created_at=pr.get("created_at"),
                        updated_at=pr.get("updated_at"),
                        html_url=pr.get("html_url"),
                    ).model_dump(exclude_none=True),
                ),
            )
            was_new = pr_entity.created_at == pr_entity.updated_at
            if was_new:
                result.entities_created += 1
            else:
                result.entities_updated += 1

            # AUTHORED edge: author -> PR
            user = pr.get("user") or {}
            author_login = user.get("login")
            if author_login:
                author_id = person_map.get(author_login)
                if not author_id:
                    author_source_ids: dict[str, str] = {"github": author_login}
                    if user.get("id"):
                        author_source_ids["github_id"] = str(user["id"])
                    author_entity = await resolve_or_create_person(
                        db,
                        org_id=org_id,
                        source=SourceType.GITHUB,
                        source_ids=author_source_ids,
                        canonical_name=author_login,
                        properties=GitHubContributorProperties(
                            login=author_login,
                            avatar_url=user.get("avatar_url"),
                            html_url=user.get("html_url"),
                        ).model_dump(exclude_none=True),
                    )
                    author_id = author_entity.id
                    person_map[author_login] = author_id

                edge = await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=author_id,
                        to_entity_id=pr_entity.id,
                        type=EdgeType.AUTHORED,
                        evidence=[{"source": "github", "pr": source_id, "field": "author"}],
                    ),
                )
                track_edge_result(edge, result)

            # Emit event for auto-linking and task transitions
            from src.events import EntityUpserted, bus

            await bus.emit(
                EntityUpserted(
                    db=db,
                    org_id=org_id,
                    entity_id=pr_entity.id,
                    entity_type=EntityType.COMMIT_PR,
                    source=SourceType.GITHUB,
                    was_created=was_new,
                    properties=pr_entity.properties,
                )
            )

            # MENTIONED_IN edges: reviewers -> PR
            for reviewer in pr.get("requested_reviewers") or []:
                reviewer_login = reviewer.get("login")
                if not reviewer_login:
                    continue
                reviewer_id = person_map.get(reviewer_login)
                if not reviewer_id:
                    reviewer_source_ids: dict[str, str] = {"github": reviewer_login}
                    if reviewer.get("id"):
                        reviewer_source_ids["github_id"] = str(reviewer["id"])
                    rev_entity = await resolve_or_create_person(
                        db,
                        org_id=org_id,
                        source=SourceType.GITHUB,
                        source_ids=reviewer_source_ids,
                        canonical_name=reviewer_login,
                        properties=GitHubContributorProperties(
                            login=reviewer_login,
                            avatar_url=reviewer.get("avatar_url"),
                            html_url=reviewer.get("html_url"),
                        ).model_dump(exclude_none=True),
                    )
                    reviewer_id = rev_entity.id
                    person_map[reviewer_login] = reviewer_id

                edge = await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=reviewer_id,
                        to_entity_id=pr_entity.id,
                        type=EdgeType.MENTIONED_IN,
                        evidence=[
                            {
                                "source": "github",
                                "pr": source_id,
                                "field": "requested_reviewer",
                            }
                        ],
                    ),
                )
                track_edge_result(edge, result)

    async def _sync_deployments(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        repo_full_name: str,
        result: ConnectorSyncResult,
        since: datetime | None,
    ) -> None:
        url = f"{API_BASE}/repos/{repo_full_name}/deployments"
        params: dict[str, str] = {"per_page": "100"}
        if since:
            params["since"] = since.isoformat()

        async for deploy in self._paginate(client, url, params=params):
            deploy_id = str(deploy["id"])
            source_id = f"{repo_full_name}/deploy/{deploy_id}"
            environment = deploy.get("environment", "unknown")
            sha = deploy.get("sha", "")[:12]

            deploy_entity = await upsert_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.DEPLOY,
                    source=SourceType.GITHUB,
                    source_ids={"github": source_id},
                    canonical_name=f"Deploy {sha} to {environment}",
                    properties=GitHubDeploymentProperties(
                        repo=repo_full_name,
                        environment=environment,
                        sha=deploy.get("sha", ""),
                        ref=deploy.get("ref"),
                        task=deploy.get("task"),
                        description=deploy.get("description"),
                        created_at=deploy.get("created_at"),
                        creator_login=(deploy.get("creator") or {}).get("login"),
                    ).model_dump(exclude_none=True),
                ),
            )
            was_new = deploy_entity.created_at == deploy_entity.updated_at
            if was_new:
                result.entities_created += 1
            else:
                result.entities_updated += 1

            # SHIPS_TO edge: if we can match the deploy sha to a merged PR
            # We look for a PR entity whose head sha matches the deployment sha
            if deploy.get("sha"):
                pr_entity = await get_entity_by_source(
                    db, org_id, SourceType.GITHUB, f"{repo_full_name}#{deploy.get('ref', '')}"
                )
                if pr_entity:
                    edge = await upsert_edge(
                        db,
                        EdgeCreate(
                            org_id=org_id,
                            from_entity_id=pr_entity.id,
                            to_entity_id=deploy_entity.id,
                            type=EdgeType.SHIPS_TO,
                            evidence=[
                                {
                                    "source": "github",
                                    "sha": deploy.get("sha"),
                                    "environment": environment,
                                }
                            ],
                        ),
                    )
                    track_edge_result(edge, result)

    # ── webhook event handlers ────────────────────────────────────────

    async def _handle_pr_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
        result: ConnectorSyncResult,
    ) -> None:
        pr = payload["pull_request"]
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        pr_number = pr["number"]
        source_id = f"{repo_full_name}#{pr_number}"

        entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.COMMIT_PR,
                source=SourceType.GITHUB,
                source_ids={"github": source_id},
                canonical_name=f"PR #{pr_number}: {pr['title']}",
                properties=GitHubPRProperties(
                    repo=repo_full_name,
                    number=pr_number,
                    title=pr["title"],
                    body=pr.get("body"),
                    state=pr["state"],
                    draft=pr.get("draft", False),
                    merged=pr.get("merged", False) or bool(pr.get("merged_at")),
                    merged_at=pr.get("merged_at"),
                    head_branch=(pr.get("head") or {}).get("ref"),
                    base_branch=(pr.get("base") or {}).get("ref"),
                    requested_reviewers=[
                        r.get("login") for r in (pr.get("requested_reviewers") or []) if r.get("login")
                    ]
                    or None,
                    created_at=pr.get("created_at"),
                    updated_at=pr.get("updated_at"),
                    html_url=pr.get("html_url"),
                    author=(pr.get("user") or {}).get("login"),
                ).model_dump(exclude_none=True),
            ),
        )
        was_new = entity.created_at == entity.updated_at
        if was_new:
            result.entities_created += 1
        else:
            result.entities_updated += 1

        # Emit event for author linking, auto-linking, and task transitions
        from src.events import EntityUpserted, bus

        await bus.emit(
            EntityUpserted(
                db=db,
                org_id=org_id,
                entity_id=entity.id,
                entity_type=EntityType.COMMIT_PR,
                source=SourceType.GITHUB,
                was_created=was_new,
                properties=entity.properties,
            )
        )

    async def _handle_deployment_status_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
        result: ConnectorSyncResult,
    ) -> None:
        deployment = payload.get("deployment", {})
        status = payload.get("deployment_status", {})
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        deploy_id = str(deployment.get("id", ""))
        source_id = f"{repo_full_name}/deploy/{deploy_id}"

        entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DEPLOY,
                source=SourceType.GITHUB,
                source_ids={"github": source_id},
                canonical_name=f"Deploy {deployment.get('sha', '')[:12]} to {deployment.get('environment', 'unknown')}",
                properties=GitHubDeploymentProperties(
                    repo=repo_full_name,
                    environment=deployment.get("environment", "unknown"),
                    sha=deployment.get("sha", ""),
                    status=status.get("state"),
                    description=status.get("description"),
                ).model_dump(exclude_none=True),
            ),
        )
        was_new = entity.created_at == entity.updated_at
        if was_new:
            result.entities_created += 1
        else:
            result.entities_updated += 1

    async def _handle_push_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
        result: ConnectorSyncResult,
    ) -> None:
        """Record push commits as evidence on the pusher's person entity."""
        pusher_login = payload.get("sender", {}).get("login")
        if not pusher_login:
            return

        person = await get_entity_by_source(db, org_id, SourceType.GITHUB, pusher_login)
        if not person:
            return

        commits = payload.get("commits", [])
        repo_full_name = payload.get("repository", {}).get("full_name", "")
        push_summary = {
            "repo": repo_full_name,
            "ref": payload.get("ref"),
            "commit_count": len(commits),
            "head_sha": payload.get("after", "")[:12],
        }
        recent_pushes = list(person.properties.get("recent_pushes", []))
        recent_pushes.append(push_summary)
        person.properties = {**person.properties, "recent_pushes": recent_pushes[-20:]}
        result.entities_updated += 1

    # ── helpers ───────────────────────────────────────────────────────

    async def _get_pr_review_state(
        self,
        client: httpx.AsyncClient,
        repo_full_name: str,
        pr_number: int,
    ) -> str | None:
        """Fetch the overall review state for a PR by looking at the latest review per reviewer.

        Returns "approved", "changes_requested", "commented", or None if no reviews.
        """
        url = f"{API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/reviews"
        try:
            resp = await client.get(url, params={"per_page": "100"})
            resp.raise_for_status()
            reviews = resp.json()
        except Exception:
            return None

        if not reviews:
            return None

        # Collapse to latest review per reviewer
        latest_by_user: dict[str, str] = {}
        for review in reviews:
            user = (review.get("user") or {}).get("login", "")
            state = review.get("state", "").lower()
            if state in ("approved", "changes_requested", "commented", "dismissed"):
                latest_by_user[user] = state

        if not latest_by_user:
            return None

        states = set(latest_by_user.values())
        if "changes_requested" in states:
            return "changes_requested"
        if "approved" in states:
            return "approved"
        return "commented"

    async def _get_pr_commit_messages(
        self,
        client: httpx.AsyncClient,
        repo_full_name: str,
        pr_number: int,
    ) -> list[str] | None:
        """Fetch meaningful commit messages for a PR.

        Filters out merge commits and very short messages. Returns the first
        line of each commit message, or None if no meaningful messages.
        """
        url = f"{API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/commits"
        try:
            resp = await client.get(url, params={"per_page": "100"})
            resp.raise_for_status()
            commits = resp.json()
        except Exception:
            return None

        messages: list[str] = []
        for c in commits:
            msg = (c.get("commit") or {}).get("message", "").split("\n")[0]
            if msg and not msg.startswith("Merge ") and len(msg) > 10:
                messages.append(msg)
        return messages or None

    async def _get_user_orgs(self, client: httpx.AsyncClient) -> list[dict]:
        resp = await client.get(f"{API_BASE}/user/orgs", params={"per_page": "100"})
        resp.raise_for_status()
        return resp.json()

    async def _get_org_repos(self, client: httpx.AsyncClient, org_login: str) -> list[dict]:
        repos: list[dict] = []
        async for repo in self._paginate(
            client, f"{API_BASE}/orgs/{org_login}/repos", params={"per_page": "100", "type": "all"}
        ):
            repos.append(repo)
        return repos

    async def _get_user_repos(self, client: httpx.AsyncClient) -> list[dict]:
        """Fetch all repos accessible to the authenticated user (owned, collaborator, org member)."""
        repos: list[dict] = []
        async for repo in self._paginate(
            client, f"{API_BASE}/user/repos", params={"per_page": "100", "sort": "updated"}
        ):
            repos.append(repo)
        return repos

    @staticmethod
    async def _paginate(
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, str] | None = None,
    ) -> AsyncIterator[Any]:
        """Paginate through GitHub REST API responses using the Link header."""
        params = dict(params or {})
        next_url: str | None = url

        while next_url:
            resp = await client.get(next_url, params=params if next_url == url else None)
            resp.raise_for_status()
            data = resp.json()

            if isinstance(data, list):
                for item in data:
                    yield item
            else:
                # Some endpoints return a wrapper object
                break

            # Parse Link header for next page
            next_url = None
            link_header = resp.headers.get("link", "")
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    # Extract URL between < and >
                    start = part.index("<") + 1
                    end = part.index(">")
                    next_url = part[start:end]
                    break
