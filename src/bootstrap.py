"""Create the first organization, admin, and API key on a fresh install.

Numen's only interactive sign-in is Google OAuth, which means a self-hoster who
has just run `docker compose up` has a working stack, an empty database, and no
way to create the first user. This closes that gap without requiring an OAuth
app: it creates the org and its admin directly, and hands back an API key that
works immediately against the MCP server and `/api/ask`.

Run it through `scripts/bootstrap_admin.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.mcp.auth import create_api_key
from src.shared.models import Organization, OrgMember, User
from src.shared.types import RoleType

# Deliberately permissive - this is a typo guard, not an address validator.
# One @, something either side, and a dot in the domain.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

# API keys minted here do not expire. A self-hoster's admin key living in a
# config file should not silently stop working 90 days after setup; the web
# flow's rotating keys are the right default for people, not for installs.
_KEY_NAME = "bootstrap admin key"


class BootstrapError(Exception):
    """The bootstrap cannot proceed with the given input."""


@dataclass(frozen=True)
class BootstrapResult:
    org_id: UUID
    user_id: UUID
    org_name: str
    email: str
    api_key: str
    created_org: bool
    created_user: bool


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "numen"


async def bootstrap_admin(
    db: AsyncSession,
    *,
    email: str,
    org_name: str | None = None,
) -> BootstrapResult:
    """Create (or reuse) the org and its admin, and mint an API key.

    Idempotent: running it again reuses the existing user and organization and
    mints a fresh key, because the previous key was shown once and is not
    recoverable.
    """
    email = (email or "").strip().lower()
    if not _EMAIL.match(email):
        raise BootstrapError(f"Not a usable email address: {email!r}")

    domain = email.split("@", 1)[1]
    org_name = (org_name or domain).strip() or domain

    existing_user = (
        await db.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()

    existing_org = (
        await db.execute(select(Organization).where(Organization.slug == _slugify(org_name)))
    ).scalar_one_or_none()

    if existing_org is not None:
        org = existing_org
        created_org = False
    else:
        # Ids are assigned here rather than left to the column default so the
        # returned result is populated without depending on flush ordering.
        org = Organization(
            id=uuid4(), name=org_name, slug=_slugify(org_name), domain=domain
        )
        db.add(org)
        await db.flush()
        created_org = True

    if existing_user is not None:
        user = existing_user
        created_user = False
    else:
        user = User(id=uuid4(), email=email, display_name=email.split("@", 1)[0])
        db.add(user)
        await db.flush()
        created_user = True

    # The first person has to be able to connect sources and add members, so
    # they get an admin role rather than the ENGINEER default.
    existing_member = (
        await db.execute(
            select(OrgMember).where(OrgMember.org_id == org.id, OrgMember.email == email)
        )
    ).scalar_one_or_none()

    if existing_member is None:
        db.add(
            OrgMember(
                org_id=org.id,
                user_id=user.id,
                email=email,
                display_name=user.display_name,
                role=RoleType.CTO,
            )
        )
        await db.flush()

    plaintext, _ = await create_api_key(
        db,
        org_id=org.id,
        name=_KEY_NAME,
        user_id=user.id,
        expires_in_days=None,
    )

    await db.commit()

    return BootstrapResult(
        org_id=org.id,
        user_id=user.id,
        org_name=org_name,
        email=email,
        api_key=plaintext,
        created_org=created_org,
        created_user=created_user,
    )
