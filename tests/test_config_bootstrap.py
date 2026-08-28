"""Tests for first-run secret bootstrapping.

`cp .env.example .env && docker compose up` is the documented quick start
and has to work. It also must not become a way to run production on a
publicly-known key.
"""

import json

import pytest

from src.config import (
    PLACEHOLDER_SECRET,
    Settings,
    bootstrap_dev_secrets,
    validate_production_config,
)


def _settings(**overrides) -> Settings:
    base = {
        "environment": "development",
        "secret_key": PLACEHOLDER_SECRET,
        "jwt_secret_key": "",
        "encryption_key": "",
    }
    base.update(overrides)
    return Settings(**base)


def test_dev_boot_replaces_the_placeholder_secret(tmp_path):
    settings = _settings()
    bootstrap_dev_secrets(settings, store=tmp_path / "dev-secrets.json")

    assert settings.secret_key != PLACEHOLDER_SECRET
    assert len(settings.secret_key) >= 32


def test_dev_boot_fills_a_missing_jwt_secret(tmp_path):
    settings = _settings()
    bootstrap_dev_secrets(settings, store=tmp_path / "dev-secrets.json")

    assert len(settings.jwt_secret_key) >= 32


def test_generated_secrets_survive_a_restart(tmp_path):
    """Regenerating on every boot would sign out every dev session."""
    store = tmp_path / "dev-secrets.json"

    first = _settings()
    bootstrap_dev_secrets(first, store=store)

    second = _settings()
    bootstrap_dev_secrets(second, store=store)

    assert first.secret_key == second.secret_key
    assert first.jwt_secret_key == second.jwt_secret_key


def test_explicit_values_are_never_overwritten(tmp_path):
    settings = _settings(secret_key="my-own-strong-secret", jwt_secret_key="x" * 40)
    bootstrap_dev_secrets(settings, store=tmp_path / "dev-secrets.json")

    assert settings.secret_key == "my-own-strong-secret"
    assert settings.jwt_secret_key == "x" * 40


def test_production_generates_nothing(tmp_path):
    """A production instance must fail loudly, not invent a key."""
    store = tmp_path / "dev-secrets.json"
    settings = _settings(environment="production")
    bootstrap_dev_secrets(settings, store=store)

    assert settings.secret_key == PLACEHOLDER_SECRET
    assert not store.exists()


def test_store_is_not_world_readable(tmp_path):
    store = tmp_path / "dev-secrets.json"
    bootstrap_dev_secrets(_settings(), store=store)

    assert store.exists()
    assert json.loads(store.read_text())["secret_key"]
    assert store.stat().st_mode & 0o077 == 0, "dev secrets must not be readable by others"


def test_unwritable_store_still_boots(tmp_path):
    """A read-only filesystem should not stop a developer starting up."""
    settings = _settings()
    bootstrap_dev_secrets(settings, store=tmp_path / "no-such-dir" / "nested" / "s.json")

    assert settings.secret_key != PLACEHOLDER_SECRET


def test_validation_passes_after_bootstrap(tmp_path, monkeypatch):
    settings = _settings()
    bootstrap_dev_secrets(settings, store=tmp_path / "dev-secrets.json")

    monkeypatch.setattr("src.config.settings", settings)
    validate_production_config()


def test_production_still_rejects_the_placeholder(monkeypatch):
    settings = _settings(environment="production", jwt_secret_key="y" * 40, encryption_key="z" * 32)
    monkeypatch.setattr("src.config.settings", settings)

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        validate_production_config()


def test_production_still_requires_a_jwt_secret(monkeypatch):
    settings = _settings(environment="production", secret_key="strong", jwt_secret_key="short")
    monkeypatch.setattr("src.config.settings", settings)

    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        validate_production_config()
