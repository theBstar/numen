"""Role-based access control helpers.

Consolidates role sets that were previously duplicated across
src/api/routes.py and src/api/routes_dashboard.py, and provides a
`require_role(*allowed)` dependency factory for gating sensitive
mutations at the route level.

Admin-email users (ADMIN_EMAILS env var) bypass role checks by design
- same pattern as src/api/routes.py update_member.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_current_user, get_db, is_admin_user
from src.shared.audit import log_action_safely
from src.shared.models import OrgMember, User
from src.shared.types import RoleType

# Role groupings used across dashboard summary + destructive mutations.
GOALS_ROLES = {RoleType.PM, RoleType.CTO, RoleType.VP_ENG, RoleType.VP_PRODUCT}
TEAM_ROLES = {RoleType.EM, RoleType.CTO, RoleType.VP_ENG}
DELAYED_ROLES = {RoleType.EM, RoleType.CTO, RoleType.VP_ENG, RoleType.VP_PRODUCT}
CROSS_BLOCK_ROLES = {RoleType.EM, RoleType.CTO, RoleType.VP_ENG}
INCIDENT_ROLES = {RoleType.ENGINEER, RoleType.VP_ENG}

# Org-wide admin operations (member management, connector config, merges).
ADMIN_ROLES = {RoleType.CTO, RoleType.VP_ENG, RoleType.VP_PRODUCT}


def require_role(*allowed: RoleType):
    """Dependency factory: 403 unless member's role is in `allowed`.

    Admin-email users (ADMIN_EMAILS) bypass the role check. The bypass
    only fires when a User row was loaded from the JWT; the dev-only
    X-Member-Email path (no User) falls back to strict role checking.
    """
    allowed_set = set(allowed)

    async def _checker(
        request: Request,
        member: OrgMember = Depends(get_current_member),
        user: User | None = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> OrgMember:
        if member.role in allowed_set:
            return member
        if user is not None and is_admin_user(user):
            return member
        ip = request.client.host if request.client else None
        await log_action_safely(
            db,
            org_id=member.org_id,
            user_id=user.id if user else None,
            action="auth.authz.denied",
            resource_type="role_check",
            ip_address=ip,
            details={
                "required_roles": sorted(r.value for r in allowed_set),
                "actual_role": member.role.value if hasattr(member.role, "value") else str(member.role),
                "path": str(request.url.path),
            },
        )
        await db.commit()
        raise HTTPException(status_code=403, detail="Insufficient role")

    return _checker
