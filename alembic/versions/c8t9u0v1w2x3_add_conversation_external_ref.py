"""Let a conversation be addressed from outside the web app.

Revision ID: c8t9u0v1w2x3
Revises: b7s8t9u0v1w2
Create Date: 2026-08-28

Conversations were reachable only by their own id, which works when the
web app is the only surface. A Slack thread, a CLI session, or an API
caller instead arrives with an identifier of its own, so the row needs a
stable external reference to look up.

external_ref is namespaced by surface, e.g. "slack:C123:1690000000.000100",
and is unique per org so two orgs sharing a Slack workspace cannot collide.
Existing rows keep NULL, which the partial index ignores.

Per-statement op.execute() so asyncpg accepts the prepared statements.
"""

from alembic import op

revision = "c8t9u0v1w2x3"
down_revision = "b7s8t9u0v1w2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS external_ref VARCHAR(512)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversation_org_external_ref "
        "ON conversations (org_id, external_ref) "
        "WHERE external_ref IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_conversation_org_external_ref")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS external_ref")
