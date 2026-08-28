"""Add task_templates table for reusable task blueprints.

Revision ID: o4d5e6f7g8h9
Revises: n3c4d5e6f7g8
Create Date: 2026-04-11 00:04:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "o4d5e6f7g8h9"
down_revision = "n3c4d5e6f7g8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            name VARCHAR(200) NOT NULL,
            description TEXT,
            default_properties JSONB NOT NULL DEFAULT '{}',
            subtask_titles JSONB DEFAULT '[]',
            created_by UUID REFERENCES org_members(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_task_templates_org ON task_templates(org_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_task_templates_org")
    op.execute("DROP TABLE IF EXISTS task_templates")
