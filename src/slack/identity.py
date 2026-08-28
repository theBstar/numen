"""Map a Slack user onto a Numen principal.

Slack tells us who spoke and where. That has to become an identity the agent
core can reason about, including what the surface permits: a direct message
addresses one person, a channel post is readable by everyone in it.

Matching is by email, so a Slack user with no Numen member record gets no
principal at all rather than inheriting org-wide access.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.principal import Audience, Principal, Surface
from src.shared.models import OrgMember
from src.slack.client import get_bot_token
from src.slack.client import lookup_slack_email as _lookup

logger = logging.getLogger(__name__)


async def lookup_slack_email(db: AsyncSession, org_id: UUID, slack_user_id: str) -> str | None:
    """Read the email off a Slack profile using the org's bot token."""
    token = await get_bot_token(db, org_id)
    if not token:
        logger.warning("No Slack token for org %s; cannot identify %s", org_id, slack_user_id)
        return None
    return await _lookup(token, slack_user_id)


async def find_member_by_email(db: AsyncSession, org_id: UUID, email: str) -> OrgMember | None:
    result = await db.execute(
        select(OrgMember).where(
            OrgMember.org_id == org_id,
            func.lower(OrgMember.email) == email.lower(),
        )
    )
    return result.scalars().first()


async def principal_for_slack_user(
    db: AsyncSession,
    org_id: UUID,
    *,
    slack_user_id: str,
    is_direct_message: bool,
) -> Principal | None:
    """Resolve who is speaking, or None if they have no Numen account."""
    email = await lookup_slack_email(db, org_id, slack_user_id)
    if not email:
        return None

    member = await find_member_by_email(db, org_id, email)
    if member is None:
        logger.info("Slack user %s (%s) has no member record in org %s", slack_user_id, email, org_id)
        return None

    return Principal(
        org_id=org_id,
        user_id=member.user_id or member.id,
        email=member.email,
        surface=Surface.SLACK,
        audience=Audience.PRIVATE if is_direct_message else Audience.SHARED,
        name=member.display_name,
        member_id=member.id,
    )
