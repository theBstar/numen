import json
import logging
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Environment
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:password@localhost:5432/numen"
    database_app_url: str = "postgresql+asyncpg://numen_app:numen_app_password@localhost:5432/numen"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # FalkorDB (graph database)
    falkordb_url: str = "redis://localhost:6381"

    # App
    app_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    secret_key: str = "change-me-in-production"
    allowed_origins: str = "http://localhost:5173"

    # Encryption (OAuth tokens at rest). Empty in dev falls back to secret_key derivation.
    encryption_key: str = ""

    # Dev-only auth bypass. Never allowed when environment == "production".
    allow_header_auth: bool = False

    # Webhook signature verification. In prod must be True.
    webhook_required: bool = True

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # JWT
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 30

    # Linear OAuth
    linear_client_id: str = ""
    linear_client_secret: str = ""
    linear_signing_secret: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""
    # Dedicated HMAC key for repo webhooks. Falls back to github_client_secret,
    # then secret_key - see src/shared/webhook_secrets.py. Set this if you
    # connect GitHub with a PAT rather than an OAuth app.
    github_webhook_secret: str = ""

    # Slack OAuth
    slack_client_id: str = ""
    slack_client_secret: str = ""
    slack_signing_secret: str = ""

    # Jira OAuth (Atlassian Cloud 3LO)
    jira_client_id: str = ""
    jira_client_secret: str = ""
    jira_signing_secret: str = ""

    # LLM (suggestions, briefings, chat). Any OpenAI-compatible endpoint:
    # OpenAI, Azure, OpenRouter, Ollama, vLLM, LiteLLM. Leave llm_base_url
    # empty for OpenAI itself; set it to e.g. http://localhost:11434/v1 to
    # keep every token inside your own network.
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    embedding_model: str = ""
    # Must match the graph's vector index width; changing it requires a reindex.
    embedding_dimensions: int = 0

    # Legacy OpenAI settings. Still honoured so existing installs keep working.
    openai_api_key: str = ""
    openai_model: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    briefing_from_email: str = "briefings@example.com"

    # Signup policy. "open" (default) matches the original behaviour: any
    # business email joins or creates the org for its domain. Self-hosted
    # instances usually want "domain" with an allowlist, or "invite".
    signup_mode: str = "open"
    allowed_email_domains: str = ""  # comma list, used when signup_mode="domain"

    # Demo orgs carry synthetic data that a background job refreshes daily.
    # Off by default: a self-hosted install has no demo org, so the job would
    # only wake every minute to find nothing.
    demo_mode: bool = False

    # Admin
    admin_emails: str = ""

    def get_allowed_email_domains(self) -> list[str]:
        return [d.strip().lower() for d in self.allowed_email_domains.split(",") if d.strip()]

    # MCP
    mcp_enabled: bool = True
    # Where MCP error responses point agents for help. Set this to your own
    # runbook so a self-hosted instance does not send people elsewhere.
    mcp_docs_base_url: str = ""

    # Workers
    sync_interval_seconds: int = 300
    briefing_hour_utc: int = 13  # 8am ET / 1pm UTC

    # Analytics (platform-agnostic tracking)
    analytics_providers: str = "console"  # comma list, e.g. "posthog,console"
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"

    def get_admin_emails(self) -> list[str]:
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

# The value .env.example ships. Never allowed to reach a running instance.
PLACEHOLDER_SECRET = "change-me-in-production"
_PLACEHOLDER_JWT = "replace-me-with-48-char-random-string-from-python-secrets"
_DEV_SECRET_STORE = Path(".numen-dev-secrets.json")


def _needs_generating(value: str, placeholder: str) -> bool:
    """Only fill a gap. A value someone chose is never overwritten, even a
    weak one - silently replacing it would be more confusing than the
    explicit failure that validation already raises."""
    return not value or value == placeholder


def bootstrap_dev_secrets(target: Settings | None = None, store: Path | None = None) -> None:
    """Fill in missing development secrets so a fresh clone starts.

    `cp .env.example .env && docker compose up` shipped a placeholder
    SECRET_KEY that startup then refused, so the documented quick start
    could not boot. Outside production we generate strong values instead,
    and persist them so restarts do not sign everyone out.

    Production is untouched: there, missing secrets remain a hard failure.
    """
    target = target if target is not None else settings
    if target.is_production:
        return

    store = store if store is not None else _DEV_SECRET_STORE
    wanted = {
        "secret_key": _needs_generating(target.secret_key, PLACEHOLDER_SECRET),
        "jwt_secret_key": _needs_generating(target.jwt_secret_key, _PLACEHOLDER_JWT),
    }
    if not any(wanted.values()):
        return

    saved: dict[str, str] = {}
    try:
        if store.exists():
            saved = json.loads(store.read_text())
    except (OSError, json.JSONDecodeError):
        saved = {}

    changed = False
    for field, needed in wanted.items():
        if not needed:
            continue
        value = saved.get(field)
        if not value:
            value = secrets.token_urlsafe(48)
            saved[field] = value
            changed = True
        setattr(target, field, value)

    if changed:
        try:
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_text(json.dumps(saved, indent=2))
            store.chmod(0o600)
        except OSError:
            # A read-only filesystem is no reason not to start; the values
            # simply do not survive this process.
            logger.warning("Could not persist development secrets to %s", store)

    logger.warning(
        "Generated development secrets (%s). Set them explicitly before running in production.",
        ", ".join(field for field, needed in wanted.items() if needed),
    )


def validate_production_config() -> None:
    """Fail-fast guardrails. Called at app startup."""
    bootstrap_dev_secrets()

    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY must be set to a value at least 32 chars long. "
            "Generate one with `python -c 'import secrets; print(secrets.token_urlsafe(48))'`."
        )

    # Reject the placeholder SECRET_KEY in every environment. An instance
    # misconfigured to `environment != "production"` must not silently run
    # with a publicly-known key. Outside production the bootstrap above will
    # already have replaced it.
    if settings.secret_key == PLACEHOLDER_SECRET:
        raise RuntimeError(
            "SECRET_KEY is still the default placeholder; set a strong value before starting."
        )

    if settings.is_production:
        if settings.allow_header_auth:
            raise RuntimeError("ALLOW_HEADER_AUTH must not be enabled in production.")
        if not settings.webhook_required:
            raise RuntimeError("WEBHOOK_REQUIRED must remain True in production.")
        if not settings.encryption_key:
            raise RuntimeError("ENCRYPTION_KEY must be set in production.")
