"""Tests for who may sign in to a self-hosted instance.

The default behaviour suits a hosted product: anyone with a business email
gets an org. On a company's own instance that is a way in for anyone who
shares the domain, and a way for strangers to create orgs on someone
else's server.
"""

import pytest

from src.api.signup_policy import SignupMode, may_create_org, may_join_domain_org


def _settings(mode="open", allowed=""):
    class _S:
        signup_mode = mode
        allowed_email_domains = allowed

        def get_allowed_email_domains(self):
            return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    return _S()


# ── open: today's behaviour, the hosted default ───────────────────────


def test_open_mode_lets_anyone_join_and_create():
    settings = _settings("open")
    assert may_join_domain_org("ada@example.com", settings)
    assert may_create_org("ada@example.com", settings)


# ── domain: a single company's instance ───────────────────────────────


def test_domain_mode_admits_a_listed_domain():
    settings = _settings("domain", allowed="example.com")
    assert may_join_domain_org("ada@example.com", settings)


def test_domain_mode_refuses_an_unlisted_domain():
    settings = _settings("domain", allowed="example.com")
    assert not may_join_domain_org("stranger@elsewhere.com", settings)


def test_domain_mode_is_case_insensitive():
    settings = _settings("domain", allowed="Example.COM")
    assert may_join_domain_org("Ada@EXAMPLE.com", settings)


def test_domain_mode_never_creates_new_orgs():
    """A stranger must not be able to spin up an org on someone's server."""
    settings = _settings("domain", allowed="example.com")
    assert not may_create_org("ada@example.com", settings)


def test_domain_mode_with_no_list_admits_nobody():
    """An empty allowlist is a closed door, not an open one."""
    settings = _settings("domain", allowed="")
    assert not may_join_domain_org("ada@example.com", settings)


def test_subdomains_are_not_admitted_by_the_parent():
    settings = _settings("domain", allowed="example.com")
    assert not may_join_domain_org("ada@evil-example.com", settings)
    assert not may_join_domain_org("ada@sub.example.com", settings)


# ── invite: the strictest posture ─────────────────────────────────────


def test_invite_mode_admits_nobody_automatically():
    settings = _settings("invite")
    assert not may_join_domain_org("ada@example.com", settings)
    assert not may_create_org("ada@example.com", settings)


# ── configuration ─────────────────────────────────────────────────────


def test_unknown_mode_falls_back_to_the_safest():
    """A typo in configuration must not silently open the instance."""
    settings = _settings("nonsense")
    assert not may_join_domain_org("ada@example.com", settings)
    assert not may_create_org("ada@example.com", settings)


def test_modes_are_the_documented_three():
    assert {m.value for m in SignupMode} == {"open", "domain", "invite"}


def test_real_settings_expose_the_policy_fields():
    from src.config import settings

    assert hasattr(settings, "signup_mode")
    assert hasattr(settings, "allowed_email_domains")


def test_default_mode_is_open_for_backwards_compatibility():
    from src.config import Settings

    # Read the declared default rather than instantiating: Settings loads the
    # local .env, so `Settings().signup_mode` asserts against whatever the
    # developer happens to have configured, not against the default.
    assert Settings.model_fields["signup_mode"].default == "open"


@pytest.mark.parametrize("email", ["", "not-an-email", "@example.com", "ada@"])
def test_malformed_addresses_are_refused(email):
    settings = _settings("domain", allowed="example.com")
    assert not may_join_domain_org(email, settings)
