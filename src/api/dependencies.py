"""FastAPI dependency injection."""

from __future__ import annotations

import hashlib
import hmac
import logging
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Path, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.graph import find_person_by_email, upsert_entity
from src.shared.audit import log_action_safely
from src.shared.database import get_db  # noqa: F401 - re-exported for route dependencies
from src.shared.models import Organization, OrgMember, User
from src.shared.types import EntityCreate, EntityType, SourceType
from src.shared.webhook_secrets import github_webhook_secret

logger = logging.getLogger(__name__)


async def get_org(
    org_id: UUID = Path(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    result = await db.execute(select(Organization).where(Organization.id == org_id))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


async def get_current_user(
    authorization: str = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """Decode JWT Bearer token and return the User.

    Returns None if no Authorization header is present (allows fallback to
    X-Member-Email for dev/demo compatibility).
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]

    # Import here to avoid circular dependency at module load time
    from src.api.user_auth import decode_token

    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def get_current_user_required(
    authorization: str = Header(None, alias="Authorization"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Like get_current_user but raises 401 if not authenticated."""
    user = await get_current_user(authorization=authorization, db=db)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def is_admin_user(user: User) -> bool:
    """Check if a user is in the admin email list."""
    return user.email.lower() in settings.get_admin_emails()


async def get_current_member(
    request: Request,
    org_id: UUID = Path(..., description="Organization ID"),
    member_email: str = Header(None, alias="X-Member-Email"),
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OrgMember:
    """Get current org member.

    Auth strategy (in priority order):
    1. JWT Bearer token - look up OrgMember by user_id
    2. X-Member-Email header - look up OrgMember by email (dev/demo fallback)
    """
    ip = request.client.host if request.client else None

    # Path 1: JWT-authenticated user
    if user is not None:
        result = await db.execute(
            select(OrgMember).where(
                OrgMember.org_id == org_id,
                OrgMember.user_id == user.id,
            )
        )
        member = result.scalar_one_or_none()

        # Fallback: match by email if user_id not yet linked on this OrgMember
        if member is None:
            result = await db.execute(
                select(OrgMember).where(
                    OrgMember.org_id == org_id,
                    OrgMember.email == user.email,
                )
            )
            member = result.scalar_one_or_none()
            # Link user_id for future lookups
            if member is not None and member.user_id is None:
                member.user_id = user.id
                await db.flush()

        if not member:
            await log_action_safely(
                db,
                org_id=org_id,
                user_id=user.id,
                action="auth.authz.denied",
                resource_type="org_membership",
                ip_address=ip,
                details={"reason": "not_a_member", "path": str(request.url.path)},
            )
            await db.commit()
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        # Lazy auto-seed Person entity for existing members
        if member.person_entity_id is None:
            await ensure_person_entity_for_member(db, member)
            await db.flush()
        return member

    # Path 2: X-Member-Email header fallback (dev/demo mode only).
    # Gated on settings.allow_header_auth; startup refuses production+flag.
    if not settings.allow_header_auth:
        await log_action_safely(
            db,
            org_id=org_id,
            action="auth.authz.denied",
            resource_type="org_membership",
            ip_address=ip,
            details={"reason": "no_jwt", "path": str(request.url.path)},
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Authentication required")

    if not member_email:
        raise HTTPException(status_code=401, detail="Authentication required")
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            OrgMember.email == member_email,
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this organization")
    # Lazy auto-seed Person entity for existing members
    if member.person_entity_id is None:
        await ensure_person_entity_for_member(db, member)
        await db.flush()
    return member


async def ensure_person_entity_for_member(
    db: AsyncSession,
    member: OrgMember,
) -> None:
    """Create a Person entity for an OrgMember if one doesn't exist, and link them."""
    if member.person_entity_id is not None:
        return

    # Check if a Person entity with this email already exists in the org
    person = await find_person_by_email(db, member.org_id, member.email)

    if person is None:
        person = await upsert_entity(
            db,
            EntityCreate(
                org_id=member.org_id,
                type=EntityType.PERSON,
                source=SourceType.MANUAL,
                source_ids={"email": member.email.lower()},
                canonical_name=member.display_name or member.email.split("@")[0],
                properties={
                    "email": member.email,
                    "role": member.role.value
                    if hasattr(member.role, "value")
                    else str(member.role),
                },
            ),
        )

    member.person_entity_id = person.id


def _missing_secret(connector: str) -> HTTPException | None:
    """Fail-closed when the configured webhook secret is absent in prod."""
    if settings.webhook_required:
        logger.error("Webhook signing secret not configured for %s; refusing request", connector)
        return HTTPException(status_code=503, detail=f"{connector} webhook verification not configured")
    logger.warning("Webhook signing secret not configured for %s; dev-mode skip", connector)
    return None


async def verify_webhook_signature(request: Request) -> None:
    """Webhook HMAC verification dependency.

    Resolves `connector` from path params. Always fails closed in production
    (`WEBHOOK_REQUIRED=true`); dev can set `WEBHOOK_REQUIRED=false` to skip
    when the secret is unset.
    """
    connector = request.path_params.get("connector")
    body = await request.body()

    if connector == "slack":
        # Slack url_verification handshake: no signature yet, let the route respond.
        # We only skip for the JSON handshake body; signed events still require sig.
        if not settings.slack_signing_secret:
            exc = _missing_secret(connector)
            if exc:
                raise exc
            return
        timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
        signature = request.headers.get("X-Slack-Signature", "")
        if not timestamp or not signature:
            raise HTTPException(status_code=401, detail="Missing Slack signature headers")
        base = f"v0:{timestamp}:{body.decode()}"
        expected = (
            "v0="
            + hmac.new(
                settings.slack_signing_secret.encode(),
                base.encode(),
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")
        return

    if connector == "github":
        # Must resolve the key exactly as webhook registration does, or hooks
        # created on a deployment without a GitHub OAuth app can never verify.
        github_secret = github_webhook_secret(settings)
        if not github_secret:
            exc = _missing_secret(connector)
            if exc:
                raise exc
            return
        signature = request.headers.get("X-Hub-Signature-256", "")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing GitHub signature header")
        expected = (
            "sha256="
            + hmac.new(
                github_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
        )
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid GitHub signature")
        return

    if connector == "linear":
        if not settings.linear_signing_secret:
            exc = _missing_secret(connector)
            if exc:
                raise exc
            return
        signature = request.headers.get("Linear-Signature", "")
        if not signature:
            raise HTTPException(status_code=401, detail="Missing Linear signature header")
        expected = hmac.new(
            settings.linear_signing_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid Linear signature")
        return

    if connector == "jira":
        # Atlassian Cloud webhooks don't sign payloads. We pass a shared secret as
        # a query string parameter when registering the webhook URL, and verify it
        # here. The secret is the configured ``jira_signing_secret``.
        if not settings.jira_signing_secret:
            exc = _missing_secret(connector)
            if exc:
                raise exc
            return
        provided = request.query_params.get("secret", "")
        if not provided or not hmac.compare_digest(provided, settings.jira_signing_secret):
            raise HTTPException(status_code=401, detail="Invalid Jira webhook secret")
        return

    raise HTTPException(status_code=404, detail=f"Unknown connector: {connector}")
