"""Add kanban_settings table for board column configuration.

Revision ID: n3c4d5e6f7g8
Revises: m2b3c4d5e6f7
Create Date: 2026-04-11 00:03:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "n3c4d5e6f7g8"
down_revision = "m2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE kanban_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            project_id UUID,
            column_status VARCHAR(50) NOT NULL,
            wip_limit INT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(org_id, project_id, column_status)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kanban_settings")
