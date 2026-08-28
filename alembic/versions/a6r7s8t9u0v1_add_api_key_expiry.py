"""Add expires_at to api_keys for default 90d rotation.

Revision ID: a6r7s8t9u0v1
Revises: z5q6r7s8t9u0
Create Date: 2026-05-04

WS3: web-flow SSO keys expire by default in 90 days. Mac SSO keys and
keys created via the existing /api/orgs/{org_id}/api-keys POST stay
non-expiring for back-compat (NULL expires_at = never expires).

Per-statement op.execute() so asyncpg accepts the prepared statements.
"""

from alembic import op

revision = "a6r7s8t9u0v1"
down_revision = "z5q6r7s8t9u0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL")
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_api_keys_expires_at
            ON api_keys (expires_at)
            WHERE expires_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_api_keys_expires_at")
    op.execute("ALTER TABLE api_keys DROP COLUMN IF EXISTS expires_at")
