"""GitHub webhook HMAC secrets must be symmetric.

Numen registered repo webhooks with ``github_client_secret or secret_key`` but
verified incoming deliveries against ``github_client_secret`` alone. A deployment
without a GitHub OAuth app - a self-hoster using a PAT, which is the common case -
therefore signed with one key and checked against another, and every delivery was
rejected. The OAuth client secret is also the wrong key to reuse: rotating the
OAuth app silently invalidates every webhook already registered on GitHub.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from src.config import Settings
from src.shared.webhook_secrets import github_webhook_secret


def _settings(**overrides) -> Settings:
    """Build Settings with every field this module reads pinned explicitly.

    Settings loads from a local .env, so a test that omits a field silently
    inherits the developer's real credential and asserts against it. Every
    secret in the fallback chain is set here so these tests are hermetic.
    """
    base = {
        "secret_key": "s" * 48,
        "github_client_secret": "",
        "github_webhook_secret": "",
        "database_url": "postgresql+asyncpg://u:p@localhost/test",
    }
    base.update(overrides)
    return Settings(**base)


def test_dedicated_secret_wins_when_set():
    s = _settings(github_webhook_secret="dedicated", github_client_secret="oauth")
    assert github_webhook_secret(s) == "dedicated"


def test_falls_back_to_oauth_client_secret():
    """Existing deployments registered hooks with the client secret - keep them working."""
    s = _settings(github_client_secret="oauth")
    assert github_webhook_secret(s) == "oauth"


def test_falls_back_to_secret_key_when_no_oauth_app():
    s = _settings()
    assert github_webhook_secret(s) == "s" * 48


def test_registration_and_verification_agree_without_an_oauth_app():
    """The regression: PAT-only deployments must still verify their own signatures."""
    s = _settings()

    signing_key = github_webhook_secret(s)
    verifying_key = github_webhook_secret(s)

    body = b'{"action":"opened"}'
    signature = "sha256=" + hmac.new(signing_key.encode(), body, hashlib.sha256).hexdigest()
    expected = "sha256=" + hmac.new(verifying_key.encode(), body, hashlib.sha256).hexdigest()

    assert hmac.compare_digest(signature, expected)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"github_client_secret": "oauth"},
        {"github_webhook_secret": "dedicated"},
        {"github_webhook_secret": "dedicated", "github_client_secret": "oauth"},
    ],
)
def test_secret_is_never_empty(overrides):
    """An empty HMAC key would make every signature trivially forgeable."""
    assert github_webhook_secret(_settings(**overrides))
