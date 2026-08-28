"""Resolution of per-connector webhook HMAC secrets.

Both sides of a webhook - the code that registers the hook with the provider and
the code that verifies incoming deliveries - must derive the key the same way.
Keeping that derivation in one place is the whole point of this module: when it
lived inline, registration used ``github_client_secret or secret_key`` while
verification used ``github_client_secret`` alone, so any deployment without a
GitHub OAuth app signed with one key and checked against another.
"""

from __future__ import annotations

from src.config import Settings
from src.config import settings as default_settings


def github_webhook_secret(settings: Settings | None = None) -> str:
    """Return the HMAC key for GitHub webhook signatures.

    Preference order:

    1. ``GITHUB_WEBHOOK_SECRET`` - the right answer. A dedicated key can be
       rotated without touching the OAuth app.
    2. ``GITHUB_CLIENT_SECRET`` - what older deployments registered their hooks
       with. Honored so an upgrade does not invalidate existing hooks.
    3. ``SECRET_KEY`` - last resort for deployments with no GitHub OAuth app,
       which is the common self-hosted case when connecting via a PAT.

    Never returns an empty string; an empty HMAC key would make every signature
    forgeable.
    """
    s = settings if settings is not None else default_settings
    return s.github_webhook_secret or s.github_client_secret or s.secret_key
