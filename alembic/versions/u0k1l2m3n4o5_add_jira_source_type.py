"""add jira source type

Revision ID: u0k1l2m3n4o5
Revises: t9i0j1k2l3m4
Create Date: 2026-04-30
"""

from alembic import op

# revision identifiers
revision = "u0k1l2m3n4o5"
down_revision = "t9i0j1k2l3m4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block in
    # PostgreSQL, so we drop into autocommit for this single statement.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'jira'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type without
    # recreating the type. Leaving the value in place is harmless.
    pass
