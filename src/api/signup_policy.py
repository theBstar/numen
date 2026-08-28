"""Who may sign in, and what happens when they do.

The original behaviour suits a hosted product: any business email joins the
org for its domain, creating one if none exists. On a company's own instance
that is two problems - everyone sharing the email domain gets in without
anyone deciding to let them, and a stranger who reaches the login page gets
their own organisation on someone else's server.

``SIGNUP_MODE`` picks the posture. ``open`` keeps the original behaviour and
stays the default so existing deployments are unaffected.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SignupMode(str, Enum):
    OPEN = "open"
    """Anyone may sign in; orgs are created on demand from the email domain."""

    DOMAIN = "domain"
    """Only listed email domains, and only into an org that already exists."""

    INVITE = "invite"
    """Nobody joins automatically. Members must already have been added."""


def _mode(settings) -> SignupMode | None:
    raw = (getattr(settings, "signup_mode", "") or "").strip().lower()
    try:
        return SignupMode(raw)
    except ValueError:
        # A typo must close the door, not open it.
        logger.warning("Unknown SIGNUP_MODE %r; refusing automatic signup.", raw)
        return None


def _domain_of(email: str) -> str | None:
    if not email or email.count("@") != 1:
        return None
    local, _, domain = email.partition("@")
    if not local.strip() or not domain.strip():
        return None
    return domain.strip().lower()


def may_join_domain_org(email: str, settings) -> bool:
    """Whether this address may be added to its domain's existing org."""
    mode = _mode(settings)
    if mode is SignupMode.OPEN:
        return _domain_of(email) is not None
    if mode is SignupMode.DOMAIN:
        domain = _domain_of(email)
        if domain is None:
            return False
        # Exact match only: a parent domain must not admit look-alikes such
        # as evil-example.com, nor subdomains nobody listed.
        return domain in set(settings.get_allowed_email_domains())
    return False


def may_create_org(email: str, settings) -> bool:
    """Whether signing in may bring a brand new organisation into being."""
    return _mode(settings) is SignupMode.OPEN and _domain_of(email) is not None
