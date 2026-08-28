"""Living API package - Mac-app + agent-fleet endpoints under /api/living/.

All routes are scoped by the authenticated user's org_id; no org_id appears
in the URL path. Cross-org access returns 404, never 403 with a body.
"""

from src.api.living.auth import router as auth_router
from src.api.living.events import router as events_router
from src.api.living.pull_requests import router as pull_requests_router
from src.api.living.tasks import router as tasks_router

__all__ = ["auth_router", "events_router", "pull_requests_router", "tasks_router"]
