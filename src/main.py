"""Numen — FastAPI application entry point."""

import asyncio
import logging
import re
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from src.api.auth import router as auth_router

# Living (Lane B) - registers /api/living/* endpoints. Out-of-lane edit to
# main.py is required because router wiring lives here per repo convention.
from src.api.living import (
    auth_router as living_auth_router,
)
from src.api.living import (
    events_router as living_events_router,
)
from src.api.living import (
    pull_requests_router as living_pull_requests_router,
)
from src.api.living import (
    tasks_router as living_tasks_router,
)
from src.api.rate_limit import limiter
from src.api.routes import router as api_router
from src.api.routes_account_keys import router as account_keys_router
from src.api.routes_admin_mcp import router as admin_mcp_router
from src.api.routes_agent import router as agent_router
from src.api.routes_api_keys import router as api_keys_router
from src.api.routes_attachments import attachment_router
from src.api.routes_attachments import task_router as task_attachments_router
from src.api.routes_briefings import router as briefings_router
from src.api.routes_connectors import router as connectors_router
from src.api.routes_dashboard import router as dashboard_router
from src.api.routes_dispatch import router as dispatch_router
from src.api.routes_edges import router as edges_router
from src.api.routes_goals import router as goals_router
from src.api.routes_kanban import router as kanban_router
from src.api.routes_notifications import router as notifications_router
from src.api.routes_prd_proposals import router as prd_proposals_router
from src.api.routes_projects import router as projects_router
from src.api.routes_saved_views import router as saved_views_router
from src.api.routes_slack import router as slack_router
from src.api.routes_sprints import router as sprints_router
from src.api.routes_suggestions import router as suggestions_router
from src.api.routes_task_activity import router as task_activity_router
from src.api.routes_tasks import router as tasks_router
from src.api.routes_templates import router as templates_router
from src.api.schemas import HealthResponse, RootResponse
from src.api.security_headers import SecurityHeadersMiddleware
from src.api.user_auth import user_auth_router
from src.chat.router import router as chat_router
from src.config import settings, validate_production_config
from src.events import register_all
from src.prd.router import router as prd_router
from src.prd.wiki_router import router as wiki_router
from src.shared.database import set_current_org_id
from src.workers.briefing_scheduler import briefing_scheduler
from src.workers.demo_scheduler import demo_scheduler
from src.workers.sync_scheduler import sync_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


# Set when the MCP server is mounted below; the lifespan enters its
# session manager so streamable_http_app's task group is initialized.
_mcp_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background workers on startup, clean up on shutdown."""
    validate_production_config()

    logger.info("Numen starting up... (environment=%s)", settings.environment)

    register_all()

    async with AsyncExitStack() as stack:
        # MCP streamable_http requires its session manager's task group to be
        # running. When we mount the inner Starlette app inside FastAPI, its
        # own lifespan never fires, so we run the session manager here.
        if _mcp_server is not None:
            await stack.enter_async_context(_mcp_server.session_manager.run())

        sync_task = asyncio.create_task(sync_scheduler.run())
        briefing_task = asyncio.create_task(briefing_scheduler.run())
        demo_task = asyncio.create_task(demo_scheduler.run())

        try:
            yield
        finally:
            logger.info("Numen shutting down...")
            try:
                from src.analytics.registry import get_tracker

                await get_tracker().flush()
                await get_tracker().shutdown()
            except Exception as e:
                logger.warning("Analytics shutdown failed: %s", e)

            from src.graph.falkor_client import close_falkor

            await close_falkor()
            sync_scheduler.stop()
            briefing_scheduler.stop()
            demo_scheduler.stop()
            sync_task.cancel()
            briefing_task.cancel()
            demo_task.cancel()
            for t in (sync_task, briefing_task, demo_task):
                try:
                    await t
                except asyncio.CancelledError:
                    pass


app = FastAPI(
    title="Numen",
    description="Proactive work intelligence platform - the context graph for organisations",
    version="0.1.0",
    lifespan=lifespan,
    # Behind CloudFront, Starlette builds redirect Locations from the viewer
    # Host but the app-internal path (no /server prefix, http scheme). That
    # 307 lands in nowhere and trips browser Mixed Content. Disable the
    # auto-redirect: the client must hit the canonical path (no trailing
    # slash) directly, matching what the frontend sends.
    redirect_slashes=False,
    openapi_tags=[
        {"name": "auth", "description": "Authentication and connector OAuth"},
        {"name": "organizations", "description": "Organization management"},
        {"name": "members", "description": "Organization members"},
        {"name": "entities", "description": "Entity CRUD and context graph"},
        {"name": "edges", "description": "Edge management"},
        {"name": "goals", "description": "Goal management and OKRs"},
        {"name": "projects", "description": "Project management"},
        {"name": "tasks", "description": "Task management"},
        {"name": "briefings", "description": "Daily briefings and urgency"},
        {"name": "connectors", "description": "Integration connector status"},
        {"name": "graph", "description": "Graph neighborhood queries"},
        {"name": "dispatch", "description": "Claude AI dispatch actions"},
        {"name": "mcp", "description": "MCP server and API key management"},
        {"name": "chat", "description": "AI chat agent"},
        {"name": "prds", "description": "PRD document system"},
        {"name": "wiki", "description": "Living product wiki - computed view over PRD graph"},
        {"name": "webhooks", "description": "Webhook receivers for connectors"},
        {"name": "people", "description": "People and org graph"},
        {"name": "health", "description": "Health and status checks"},
    ],
)

_ORG_ID_PATTERN = re.compile(r"/api/orgs/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


class RLSMiddleware(BaseHTTPMiddleware):
    """Extract org_id from URL path and set it as the RLS context variable."""

    async def dispatch(self, request: Request, call_next) -> Response:
        match = _ORG_ID_PATTERN.search(request.url.path)
        if match:
            set_current_org_id(match.group(1))
        try:
            response = await call_next(request)
        finally:
            set_current_org_id(None)
        return response


_allowed_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if not _allowed_origins:
    logger.warning("ALLOWED_ORIGINS is empty — CORS will reject all cross-origin requests")

_cors_allow_headers = ["Authorization", "Content-Type"]
if settings.allow_header_auth:
    _cors_allow_headers.append("X-Member-Email")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=_cors_allow_headers,
    expose_headers=["Content-Type"],
    max_age=600,
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security headers on every response.
app.add_middleware(SecurityHeadersMiddleware)

# RLS middleware must be added AFTER CORSMiddleware so that CORS headers
# are always present (Starlette processes last-added middleware outermost).
app.add_middleware(RLSMiddleware)


# Global exception handler ensures CORS headers are present on error responses.
# Without this, unhandled exceptions propagating through BaseHTTPMiddleware
# can bypass CORSMiddleware header injection.
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(auth_router)
app.include_router(user_auth_router)
app.include_router(api_router)
app.include_router(edges_router)
app.include_router(goals_router)
app.include_router(projects_router)
app.include_router(tasks_router)
app.include_router(task_activity_router)
app.include_router(saved_views_router)
app.include_router(kanban_router)
app.include_router(sprints_router)
app.include_router(templates_router)
app.include_router(notifications_router)
app.include_router(task_attachments_router)
app.include_router(attachment_router)
app.include_router(briefings_router)
app.include_router(connectors_router)
app.include_router(suggestions_router)
app.include_router(dispatch_router)
app.include_router(dashboard_router)
app.include_router(chat_router)
app.include_router(agent_router)
app.include_router(slack_router)
app.include_router(prd_router)
app.include_router(wiki_router)
app.include_router(api_keys_router)
app.include_router(living_tasks_router)
app.include_router(living_events_router)
app.include_router(living_pull_requests_router)
app.include_router(living_auth_router)
app.include_router(admin_mcp_router)
app.include_router(account_keys_router)
app.include_router(prd_proposals_router)

# Mount MCP server (Streamable HTTP transport) if enabled.
# Streamable HTTP serves the full MCP protocol on a single POST endpoint, which
# is what `claude mcp add --transport http` and other modern MCP clients expect.
# Older SSE clients should be reconfigured via the MCP Setup page.
if settings.mcp_enabled:
    try:
        from src.mcp.server import create_mcp_server

        _mcp_server = create_mcp_server()
        app.mount("/mcp", _mcp_server.streamable_http_app())
        logger.info("MCP server mounted at /mcp (streamable_http)")
    except ImportError:
        logger.warning("MCP package not installed - skipping MCP server mount")


@app.get(
    "/",
    response_model=RootResponse,
    tags=["health"],
    summary="API root",
)
async def root():
    """Returns API name, version, and documentation URL."""
    return {
        "name": "Numen",
        "version": "0.2.0",
        "description": "Proactive work intelligence platform - the context graph for organisations",
        "docs": f"{settings.app_url}/docs",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Health check",
)
async def health():
    """Returns service health status."""
    return {"status": "ok"}
