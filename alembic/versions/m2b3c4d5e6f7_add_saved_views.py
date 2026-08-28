"""Add saved_views table for user-defined filtered views.

Revision ID: m2b3c4d5e6f7
Revises: l1a2b3c4d5e6
Create Date: 2026-04-11 00:02:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "m2b3c4d5e6f7"
down_revision = "l1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE saved_views (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            member_id UUID NOT NULL REFERENCES org_members(id),
            name VARCHAR(200) NOT NULL,
            entity_type VARCHAR(50) NOT NULL DEFAULT 'task',
            filters JSONB NOT NULL DEFAULT '{}',
            sort_config JSONB DEFAULT '{}',
            view_mode VARCHAR(20) DEFAULT 'list',
            group_by VARCHAR(50),
            is_default BOOLEAN DEFAULT FALSE,
            is_shared BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_saved_views_org_member ON saved_views(org_id, member_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_saved_views_org_member")
    op.execute("DROP TABLE IF EXISTS saved_views")
