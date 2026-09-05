"""Numen MCP server - FastMCP instance with dual transport (SSE + stdio)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config import settings
from src.mcp import observability as mcp_obs
from src.mcp import resources as mcp_resources
from src.mcp import tools as mcp_tools
from src.mcp.errors import ErrorCode, error_response
from src.mcp.token_verifier import NumenTokenVerifier, decode_client_id
from src.shared.database import async_session

logger = logging.getLogger(__name__)


@dataclass
class NumenContext:
    """Application context yielded by the MCP lifespan."""

    session_factory: async_sessionmaker[AsyncSession]


@asynccontextmanager
async def numen_lifespan(server: FastMCP) -> AsyncIterator[NumenContext]:
    """Provide the SQLAlchemy session factory to MCP tools."""
    logger.info("Numen MCP server starting up")
    try:
        yield NumenContext(session_factory=async_session)
    finally:
        logger.info("Numen MCP server shutting down")


def _get_actor() -> tuple[str | None, str | None]:
    """Return (org_id, user_id) for the current request, both as strings.

    user_id is None for legacy keys that predate the user_id column; write
    tools refuse those via _require_write().
    """
    token = get_access_token()
    if not token:
        return None, None
    return decode_client_id(token.client_id)


def _verify_org_access(org_id: str, *, require_auth: bool = False) -> str | None:
    """Verify org_id matches the authenticated key. Returns error JSON or None.

    DEPRECATED for new tools - use _resolve_org_uuid() which both resolves
    org_id from the auth context (so callers don't need to pass it) AND
    validates explicit values. Kept for backwards compatibility.

    Args:
        org_id: The org_id provided by the tool caller.
        require_auth: If True, reject the call when no auth token is present
                      (defense-in-depth for SSE transport).
    """
    auth_org, _ = _get_actor()
    if auth_org is None:
        if require_auth:
            return error_response(
                ErrorCode.AUTH_REQUIRED,
                message="No API key on this request.",
                hint="Add Authorization: Bearer <numen_...> header, or run via stdio.",
            )
        return None  # stdio mode - no auth available
    if auth_org != org_id:
        return error_response(
            ErrorCode.ORG_MISMATCH,
            message="org_id does not match authenticated API key.",
            hint="Omit org_id - the server resolves it from your API key.",
        )
    return None


def _resolve_org_uuid(
    org_id: str | None, *, require_auth: bool = False
) -> tuple[UUID | None, str | None]:
    """Resolve the org for this request. Auth context wins over caller-supplied.

    Returns (org_uuid, None) on success, (None, error_json) on failure.

    Behavior:
    - If auth context has org_id (SSE mode): that wins. If caller also passed
      org_id and it doesn't match, return ORG_MISMATCH (defense in depth).
    - If no auth context (stdio mode): caller must supply org_id.
    - If neither auth context nor caller-supplied: ORG_ID_REQUIRED (or
      AUTH_REQUIRED when require_auth=True).
    """
    auth_org_str, _ = _get_actor()
    chosen: str | None
    if auth_org_str is not None:
        if org_id is not None and org_id != auth_org_str:
            return None, error_response(
                ErrorCode.ORG_MISMATCH,
                message="org_id does not match authenticated API key.",
                hint="Omit org_id - the server resolves it from your API key.",
            )
        chosen = auth_org_str
    else:
        if require_auth:
            return None, error_response(
                ErrorCode.AUTH_REQUIRED,
                message="No API key on this request.",
                hint="Add Authorization: Bearer <numen_...> header, or run via stdio.",
            )
        if org_id is None:
            return None, error_response(
                ErrorCode.ORG_ID_REQUIRED,
                message="org_id is required in stdio mode (no API key bound).",
                hint="Pass org_id explicitly when calling without authentication.",
            )
        chosen = org_id
    try:
        return UUID(chosen), None
    except (ValueError, TypeError):
        return None, error_response(
            ErrorCode.INVALID_UUID,
            message=f"org_id is not a valid UUID: {chosen!r}",
        )


def _resolve_agent_uuid(agent_id: str | None) -> tuple[UUID, str | None]:
    """Resolve the agent UUID. Auth-context user_id is the default identity.

    Returns (agent_uuid, None) on success, (UUID(int=0), error_json) on
    invalid explicit UUID. If the caller passes nothing AND there's no auth
    user_id, falls back to UUID(int=0) (synthetic agent for stdio mode).
    """
    if agent_id is not None:
        try:
            return UUID(agent_id), None
        except (ValueError, TypeError):
            return UUID(int=0), error_response(
                ErrorCode.INVALID_UUID,
                message=f"agent_id is not a valid UUID: {agent_id!r}",
            )
    _, user_id_str = _get_actor()
    if user_id_str is not None:
        try:
            return UUID(user_id_str), None
        except (ValueError, TypeError):
            pass  # corrupt user_id from auth context - shouldn't happen, fall back
    return UUID(int=0), None  # synthetic - stdio or legacy key


def _require_write(*, require_auth: bool) -> tuple[str | None, str | None]:
    """Return (error_json, user_id_str). error_json is set iff the request
    cannot perform writes (no auth or legacy key without user binding).
    """
    if not require_auth:
        # stdio (local) mode - skip user binding requirement; tools attribute
        # writes to a synthetic actor in this path.
        return None, None
    org_id, user_id = _get_actor()
    if org_id is None:
        return error_response(
            ErrorCode.AUTH_REQUIRED,
            message="No API key on this request.",
            hint="Add Authorization: Bearer <numen_...> header.",
        ), None
    if user_id is None:
        return (
            error_response(
                ErrorCode.USER_BINDING_REQUIRED,
                message=(
                    "This API key is not bound to a user. Generate a new "
                    "key from the Numen MCP Setup page to enable write tools."
                ),
                hint="Visit /mcp-setup in the Numen web app to mint a user-bound key.",
            ),
            None,
        )
    return None, user_id


def _build_transport_security() -> TransportSecuritySettings:
    """Allowlist Host headers for the deployment so DNS-rebinding protection
    doesn't 421 legitimate traffic. Hosts derived from settings.app_url plus
    localhost variants for dev. Origins are not validated here (Bearer auth
    + the Authorization header check upstream are the actual gates)."""
    parsed = urlparse(settings.app_url)
    primary = parsed.netloc or "localhost:8000"

    allowed_hosts: list[str] = [primary]

    # A reverse proxy on 80 or 443 forwards a Host header with no port, so the
    # port-stripped form has to be allowed too. Without it an authenticated MCP
    # call behind any proxy returned 421 "Invalid Host header".
    bare = primary.rsplit(":", 1)[0] if ":" in primary else primary
    allowed_hosts.append(bare)

    # If running with HTTPS, also accept the apex form ("www." stripped).
    for host in (primary, bare):
        if host.startswith("www."):
            allowed_hosts.append(host[len("www.") :])

    # Local development reaches the app directly on an arbitrary port.
    allowed_hosts += ["localhost", "127.0.0.1", "localhost:*", "127.0.0.1:*"]

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=[],  # Origin header is not required (CLI clients omit it).
    )


def create_mcp_server(*, with_auth: bool = True) -> FastMCP:
    """Create and configure the Numen FastMCP server instance.

    Args:
        with_auth: Enable Bearer token auth (True for SSE, False for stdio).
    """
    auth_kwargs: dict = {}
    if with_auth:
        auth_kwargs = {
            "auth": AuthSettings(
                issuer_url=settings.app_url,
                resource_server_url=f"{settings.app_url}/mcp",
            ),
            "token_verifier": NumenTokenVerifier(),
        }

    # streamable_http_path is the path the inner Starlette app exposes the
    # MCP endpoint on. We set it to "/" so that mounting this app at "/mcp"
    # in FastAPI yields the canonical "/mcp" URL (and not "/mcp/mcp").
    mcp = FastMCP(
        "Numen",
        streamable_http_path="/",
        transport_security=_build_transport_security(),
        instructions=(
            "Numen is a proactive work intelligence platform. All data is scoped "
            "to one organization. With an API key (SSE), org_id is automatically "
            "resolved from your key - omit it from tool calls. In stdio mode, pass "
            "org_id explicitly.\n\n"
            "When a developer starts new work, follow this flow: (1) call "
            "find_matching_task with the user's description and surface any high-"
            "confidence matches for the user to confirm before proceeding; (2) if no "
            "match is confirmed, call create_task; (3) drive the task forward with "
            "update_task_status (todo -> in_progress -> in_review -> merged -> done; "
            "backward transitions are rejected); (4) use link_task to attach it to "
            "projects/goals or mark blockers; (5) optionally call append_wiki_note to "
            "record durable learnings against existing wiki features.\n\n"
            "Read tools (search_entities, list_tasks, get_task_context, list_goals, "
            "get_urgency_scores, list_wiki_features, get_wiki_feature, ...) need no "
            "user binding. Write tools (create_*, update_*, link_*, append_wiki_note) "
            "require an API key bound to a user; generate one from the Numen MCP Setup "
            "page."
        ),
        lifespan=numen_lifespan,
        **auth_kwargs,
    )

    # Capture for use in tool closures - enforces auth at tool level too
    _require_auth = with_auth

    # ── Helper to get DB session from context ────────────────────────
    def _get_session_factory(ctx: Context) -> async_sessionmaker[AsyncSession]:
        return ctx.request_context.lifespan_context.session_factory

    # ── Tools ────────────────────────────────────────────────────────

    @mcp.tool()
    async def hello_numen(
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Start here. Returns org info, available tools grouped by intent, a
        sample first call, and your latest briefing snippet (if available).

        This is the recommended first tool an agent calls. The response is
        stable JSON; parse `sample_first_call` to auto-suggest the next step.

        Args:
            org_id: Optional - automatically resolved from API key over SSE.
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        _, user_id_str = _get_actor()
        try:
            user_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            user_uuid = None
        async with mcp_obs.track(
            tool_name="hello_numen",
            org_id=org_uuid,
            user_id=user_uuid,
            args={},
            session_factory=_get_session_factory(ctx),
        ) as _obs:
            async with _get_session_factory(ctx)() as db:
                _result = await mcp_tools.hello_numen(db, org_uuid, user_uuid)
            _obs.set_result(_result)
            return _result

    @mcp.tool()
    async def search_entities(
        query: str,
        entity_type: str | None = None,
        limit: int = 20,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Search entities by name with optional type filter.

        Args:
            org_id: Organization UUID
            query: Search term to match against entity names
            entity_type: Optional filter (task, person, goal, project, commit_pr, etc.)
            limit: Max results (default 20)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.search_entities(
                db,
                org_uuid, query, entity_type, limit)

    @mcp.tool()
    async def get_entity(
        entity_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get entity details by ID including its edges/relationships.

        Args:
            org_id: Organization UUID
            entity_id: Entity UUID
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_entity_detail(
                db,
                org_uuid, entity_id)

    @mcp.tool()
    async def get_entity_graph(
        entity_id: str,
        depth: int = 2,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get the neighborhood graph for an entity (entities and edges within N hops).

        Args:
            org_id: Organization UUID
            entity_id: Entity UUID
            depth: Number of hops to traverse (1-3, default 2)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_entity_graph(
                db,
                org_uuid, entity_id, depth)

    @mcp.tool()
    async def list_tasks(
        status: str | None = None,
        priority: str | None = None,
        assignee: str | None = None,
        project_id: str | None = None,
        limit: int = 50,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """List tasks with optional filtering by status, priority, assignee, or project.

        Args:
            org_id: Organization UUID
            status: Filter by status (todo, in_progress, in_review, merged, done)
            priority: Filter by priority (urgent, high, medium, low)
            assignee: Filter by assignee name (partial match)
            project_id: Filter by project UUID
            limit: Max results (default 50)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.list_tasks(
                db,
                org_uuid, status, priority, assignee, project_id, limit)

    @mcp.tool()
    async def get_task_context(
        task_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get rich context for a task: goals, blocking chain, urgency, PRs, project.

        Args:
            org_id: Organization UUID
            task_id: Task entity UUID
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_task_context(
                db,
                org_uuid, task_id)

    @mcp.tool()
    async def list_goals(
        level: str | None = None,
        include_tree: bool = False,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """List goals, optionally as a hierarchy tree.

        Args:
            org_id: Organization UUID
            level: Filter by level (company, team, individual)
            include_tree: If true, return full parent-child hierarchy
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.list_goals(
                db,
                org_uuid, level, include_tree)

    @mcp.tool()
    async def get_goal_progress(
        goal_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get progress for a goal with linked task completion stats and key results.

        Args:
            org_id: Organization UUID
            goal_id: Goal entity UUID
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_goal_progress(
                db,
                org_uuid, goal_id)

    @mcp.tool()
    async def get_urgency_scores(
        person_name: str | None = None,
        limit: int = 10,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get top urgent items ranked by urgency score, optionally filtered by person.

        Args:
            org_id: Organization UUID
            person_name: Optional person name to filter by
            limit: Max results (default 10)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_urgency_scores(
                db,
                org_uuid, person_name, limit)

    @mcp.tool()
    async def get_briefing(
        member_email: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get the latest daily briefing for a member by email.

        Args:
            org_id: Organization UUID
            member_email: Member's email address
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_briefing(
                db,
                org_uuid, member_email)

    @mcp.tool()
    async def get_person_workload(
        person_name: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Get a person's task workload breakdown (counts by status).

        Args:
            org_id: Organization UUID
            person_name: Person name to look up
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_person_workload_tool(
                db,
                org_uuid, person_name)

    @mcp.tool()
    async def search_by_source(
        source: str,
        source_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Look up an entity by its external source system ID.

        Args:
            org_id: Organization UUID
            source: Source system (linear, github, slack, etc.)
            source_id: The ID from the source system (e.g., Linear issue ID, GitHub PR number)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.search_by_source(
                db,
                org_uuid, source, source_id)

    @mcp.tool()
    async def get_context(
        task: str,
        agent_id: str | None = None,
        task_id: str | None = None,
        max_tokens: int = 4000,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Living: retrieve task-relevant context for an agent.

        Embeds the task, runs cosine vector search over the org's graph,
        expands the parent document neighborhood, and returns chunks plus
        related entities token-budgeted to ``max_tokens``.

        Args:
            task: Free-text task description (REQUIRED)
            agent_id: Optional agent UUID for the event log. Defaults to the
                authenticated user_id over SSE; UUID(int=0) in stdio mode.
            task_id: Optional Living task UUID this fetch is part of
            max_tokens: Token budget for the returned chunk bodies
            org_id: Optional - automatically resolved from API key over SSE
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        agent_uuid, agent_err = _resolve_agent_uuid(agent_id)
        if agent_err:
            return agent_err
        _, user_id_str = _get_actor()
        try:
            user_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            user_uuid = None
        async with mcp_obs.track(
            tool_name="get_context",
            org_id=org_uuid,
            user_id=user_uuid,
            args={"max_tokens": max_tokens},
            session_factory=_get_session_factory(ctx),
        ) as _obs:
            async with _get_session_factory(ctx)() as db:
                _result = await mcp_tools.get_context(
                    db,
                    org_uuid,
                    agent_uuid,
                    task,
                    task_id=UUID(task_id) if task_id else None,
                    max_tokens=max_tokens,
                )
            _obs.set_result(_result)
            return _result

    @mcp.tool()
    async def find_matching_task(
        description: str,
        project_hint: str | None = None,
        limit: int = 10,
        recommend_threshold: float | None = 0.85,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Find existing tasks that may match a piece of new work.

        Use this BEFORE creating a task. Returns ranked candidates with
        confidence scores. When the top match's confidence >= threshold
        (default 0.85), the response includes recommended_action:
        "use_existing" plus the matched task_id - surface that to the
        user before creating a duplicate.

        Args:
            description: Free-text description of the new work
            project_hint: Optional project name hint to bias the match
            limit: Max candidates (default 10)
            recommend_threshold: Confidence cutoff for recommendation
                (default 0.85, set to null to suppress)
            org_id: Optional - automatically resolved from API key over SSE
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        _, user_id_str = _get_actor()
        try:
            user_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            user_uuid = None
        async with mcp_obs.track(
            tool_name="find_matching_task",
            org_id=org_uuid,
            user_id=user_uuid,
            args={"limit": limit, "recommend_threshold": recommend_threshold},
            session_factory=_get_session_factory(ctx),
        ) as _obs:
            async with _get_session_factory(ctx)() as db:
                _result = await mcp_tools.find_matching_task(
                    db,
                    org_uuid,
                    description,
                    project_hint,
                    limit,
                    recommend_threshold=recommend_threshold,
                )
            _obs.set_result(_result)
            return _result

    @mcp.tool()
    async def create_task(
        title: str,
        description: str | None = None,
        project_id: str | None = None,
        goal_ids: list[str] | None = None,
        assignee_email: str | None = None,
        priority: str = "medium",
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Create a new task in todo status with optional project/goal/assignee links.

        Only call this after find_matching_task confirms no existing task fits.

        Args:
            org_id: Organization UUID
            title: Task title (required)
            description: Optional task body
            project_id: Optional project UUID to attach via CONTAINS
            goal_ids: Optional goal UUIDs to attach via TAGGED_TO
            assignee_email: Optional person email to attach via ASSIGNED_TO
            priority: urgent | high | medium | low (default medium)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.create_task(
                db,
                org_uuid,
                actor_user_id,
                title=title,
                description=description,
                project_id=project_id,
                goal_ids=goal_ids,
                assignee_email=assignee_email,
                priority=priority,
            )

    @mcp.tool()
    async def update_task_status(
        task_id: str,
        status: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Move a task forward in the lifecycle. Backward transitions are rejected.

        Pipeline: todo -> in_progress -> in_review -> merged -> done.

        Args:
            org_id: Organization UUID
            task_id: Task entity UUID
            status: Target status (must be later in the pipeline than current)
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.update_task_status(
                db,
                org_uuid, actor_user_id, task_id, status
            )

    @mcp.tool()
    async def update_task(
        task_id: str,
        title: str | None = None,
        description: str | None = None,
        priority: str | None = None,
        assignee_email: str | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Patch a task's title/description/priority and optionally re-assign.

        Pass assignee_email="" to clear the current assignment. Status changes
        must use update_task_status to enforce the forward-only rule.
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.update_task(
                db,
                org_uuid,
                actor_user_id,
                task_id,
                title=title,
                description=description,
                priority=priority,
                assignee_email=assignee_email,
            )

    @mcp.tool()
    async def link_task(
        task_id: str,
        project_id: str | None = None,
        goal_ids: list[str] | None = None,
        blocks_task_id: str | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Attach a task to a project / goals, or mark it as blocking another task.

        Edges are additive and idempotent.
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.link_task(
                db,
                org_uuid,
                actor_user_id,
                task_id,
                project_id=project_id,
                goal_ids=goal_ids,
                blocks_task_id=blocks_task_id,
            )

    @mcp.tool()
    async def create_project(
        name: str,
        description: str | None = None,
        status: str = "planning",
        owner_email: str | None = None,
        goal_ids: list[str] | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Create a project. Status defaults to "planning".

        Args:
            org_id: Organization UUID
            name: Project name (required)
            description: Optional project description
            status: planning | active | paused | completed | archived
            owner_email: Optional person email to attach via OWNS
            goal_ids: Optional goal UUIDs to attach via TAGGED_TO
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.create_project(
                db,
                org_uuid,
                actor_user_id,
                name=name,
                description=description,
                status=status,
                owner_email=owner_email,
                goal_ids=goal_ids,
            )

    @mcp.tool()
    async def create_goal(
        title: str,
        level: str,
        parent_goal_id: str | None = None,
        description: str | None = None,
        target_value: float | None = None,
        owner_email: str | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Create a goal entity, optionally as a child of an existing goal.

        Args:
            org_id: Organization UUID
            title: Goal title (required)
            level: company | team | individual
            parent_goal_id: Optional parent goal UUID (creates PARENT_OF edge)
            description: Optional goal description
            target_value: Optional numeric target for the goal
            owner_email: Optional person email to attach via OWNS
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.create_goal(
                db,
                org_uuid,
                actor_user_id,
                title=title,
                level=level,
                parent_goal_id=parent_goal_id,
                description=description,
                target_value=target_value,
                owner_email=owner_email,
            )

    @mcp.tool()
    async def list_wiki_features(
        status: str | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """List wiki features (slug, title, status). Filter by status if given."""
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.list_wiki_features(
                db,
                org_uuid, status)

    @mcp.tool()
    async def get_wiki_feature(
        slug: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Fetch a wiki feature by slug, including Markdown content."""
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_wiki_feature(
                db,
                org_uuid, slug)

    @mcp.tool()
    async def append_wiki_note(
        org_id: str,
        feature_slug: str,
        note_markdown: str,
        ctx: Context = None,
    ) -> str:
        """Append a dated, attributed note to a wiki feature.

        Notes go under a "## Notes from Numen MCP" trailing section and
        survive PRD-driven regeneration. Idempotent on duplicate consecutive
        notes.
        """
        if err := _verify_org_access(org_id, require_auth=_require_auth):
            return err
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        actor_user_id = UUID(user_id) if user_id else UUID(int=0)
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.append_wiki_note(
                db, UUID(org_id), actor_user_id, feature_slug, note_markdown
            )

    @mcp.tool()
    async def update_pr_state(
        task_id: str,
        action: str,
        branch_name: str | None = None,
        base_branch: str | None = None,
        commit_sha: str | None = None,
        commit_head_sha: str | None = None,
        provider: str | None = None,
        pr_number: int | None = None,
        pr_url: str | None = None,
        draft: bool = False,
        pr_state: str | None = None,
        merge_state_status: str | None = None,
        merge_strategy: str | None = None,
        merged_commit_sha: str | None = None,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Drive the PR lifecycle for a Living task. action picks the slice.

        action="branch_pushed":
            Required: branch_name, commit_sha
            Effect:   emits BranchPushedEvent (telemetry only)

        action="link":
            Required: branch_name, base_branch, provider ("github" or "local")
            Optional: pr_number, pr_url, commit_head_sha, draft
            Effect:   upserts the LivingPullRequest row; emits PrStateChangedEvent
                      if state moved from none/closed to draft/open

        action="patch":
            Optional: pr_state, merge_state_status, commit_head_sha
            Effect:   partial update (poll cycle); emits event only if pr_state
                      actually changed

        action="merge":
            Required: merge_strategy ("squash" / "rebase" / "merge"), merged_commit_sha
            Effect:   records merge; advances task to DONE if non-terminal;
                      emits MergeCompletedEvent

        Args:
            task_id: Living task UUID
            action: one of "branch_pushed" | "link" | "patch" | "merge"
            org_id: Optional - automatically resolved from API key over SSE
        """
        write_err, _ = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        _, user_id_str = _get_actor()
        try:
            user_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            user_uuid = None
        async with mcp_obs.track(
            tool_name="update_pr_state",
            org_id=org_uuid,
            user_id=user_uuid,
            args={"action": action, "provider": provider, "draft": draft},
            session_factory=_get_session_factory(ctx),
        ) as _obs:
            async with _get_session_factory(ctx)() as db:
                _result = await mcp_tools.update_pr_state(
                    db,
                    org_uuid,
                    task_id,
                    action=action,
                    branch_name=branch_name,
                    base_branch=base_branch,
                    commit_sha=commit_sha,
                    commit_head_sha=commit_head_sha,
                    provider=provider,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    draft=draft,
                    pr_state=pr_state,
                    merge_state_status=merge_state_status,
                    merge_strategy=merge_strategy,
                    merged_commit_sha=merged_commit_sha,
                )
            _obs.set_result(_result)
            return _result

    @mcp.tool()
    async def get_pr_state(
        task_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Read the LivingPullRequest row attached to this task (or {pr: null}).

        Args:
            task_id: Living task UUID
            org_id: Optional - automatically resolved from API key over SSE
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        _, user_id_str = _get_actor()
        try:
            user_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            user_uuid = None
        async with mcp_obs.track(
            tool_name="get_pr_state",
            org_id=org_uuid,
            user_id=user_uuid,
            args={},
            session_factory=_get_session_factory(ctx),
        ) as _obs:
            async with _get_session_factory(ctx)() as db:
                _result = await mcp_tools.get_pr_state(db, org_uuid, task_id)
            _obs.set_result(_result)
            return _result

    @mcp.tool()
    async def propose_prd_update(
        feature_slug: str,
        section_anchor: str,
        diff_md: str,
        rationale: str = "",
        expires_in_days: int = 7,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Propose an edit to a wiki feature section, awaiting user approval.

        Use this when your work changes the spec. We snapshot the current
        wiki content hash; if the wiki drifts before the user approves
        (because regen ran or another approval landed), we transition the
        proposal to 'stale' and you must re-propose.

        At most one PENDING proposal per (org, feature_slug, section_anchor)
        - the second concurrent propose returns proposal_duplicate_pending.

        Args:
            feature_slug: Wiki feature slug (call list_wiki_features for valid ones)
            section_anchor: Section identifier within the feature
            diff_md: New full content for the section (treated as replacement
                in v0; markdown-diff merge deferred)
            rationale: Why you're proposing this change (shown to the user)
            expires_in_days: Auto-reject after N days without decision (1-30, default 7)
            org_id: Optional - automatically resolved from API key over SSE
        """
        write_err, user_id = _require_write(require_auth=_require_auth)
        if write_err:
            return write_err
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        actor_user_id = UUID(user_id) if user_id else None
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.propose_prd_update(
                db,
                org_uuid,
                actor_user_id,
                feature_slug,
                section_anchor,
                diff_md,
                rationale=rationale,
                expires_in_days=expires_in_days,
            )

    @mcp.tool()
    async def get_proposal_status(
        proposal_id: str,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """Read the current status of a PRD proposal you (or another agent) filed.

        Returns {proposal: {...}} or an error envelope if not found in this org.

        Args:
            proposal_id: UUID returned by propose_prd_update
            org_id: Optional - automatically resolved from API key over SSE
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.get_proposal_status(db, org_uuid, proposal_id)

    @mcp.tool()
    async def list_proposals(
        status: str | None = None,
        feature_slug: str | None = None,
        only_mine: bool = False,
        limit: int = 50,
        org_id: str | None = None,
        ctx: Context = None,
    ) -> str:
        """List PRD proposals scoped to your org.

        Args:
            status: Filter by status (pending|applied|rejected|stale|expired)
            feature_slug: Filter to one wiki feature
            only_mine: If true, scope to proposals you (the auth user) filed
            limit: Max results (default 50)
            org_id: Optional - automatically resolved from API key over SSE
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        _, user_id_str = _get_actor()
        try:
            actor_uuid = UUID(user_id_str) if user_id_str else None
        except (ValueError, TypeError):
            actor_uuid = None
        async with _get_session_factory(ctx)() as db:
            return await mcp_tools.list_proposals_tool(
                db,
                org_uuid,
                status=status,
                feature_slug=feature_slug,
                proposer_user_id=actor_uuid if only_mine else None,
                limit=limit,
            )

        # ── Resources ────────────────────────────────────────────────────

    @mcp.resource("numen://org/{org_id}/overview")
    async def org_overview(org_id: str, ctx: Context = None) -> str:
        """Organization summary: name, member count, entity counts, connected sources.

        WS6 hardening: org_id from the URI is validated against the auth
        context. Cross-org URIs return an error envelope, not the data.
        """
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_resources.get_org_overview(db, org_uuid)

    @mcp.resource("numen://org/{org_id}/goals")
    async def org_goals(org_id: str, ctx: Context = None) -> str:
        """Goal hierarchy tree with coverage statistics."""
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_resources.get_org_goals(db, org_uuid)

    @mcp.resource("numen://org/{org_id}/urgent")
    async def org_urgent(org_id: str, ctx: Context = None) -> str:
        """Top 20 urgent tasks across the organization."""
        org_uuid, err = _resolve_org_uuid(org_id, require_auth=_require_auth)
        if err:
            return err
        async with _get_session_factory(ctx)() as db:
            return await mcp_resources.get_urgent_tasks(db, org_uuid)

    return mcp


def create_sse_app():
    """Create the SSE ASGI app for mounting on FastAPI."""
    mcp = create_mcp_server(with_auth=True)
    return mcp.sse_app()


def create_streamable_http_app():
    """Create the Streamable HTTP ASGI app for mounting on FastAPI."""
    mcp = create_mcp_server(with_auth=True)
    return mcp.streamable_http_app()
