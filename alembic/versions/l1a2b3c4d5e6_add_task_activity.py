"""Add task_activity table for tracking entity-level activity.

Revision ID: l1a2b3c4d5e6
Revises: k0f1a2b3c4d5
Create Date: 2026-04-11 00:01:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "l1a2b3c4d5e6"
down_revision = "k0f1a2b3c4d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_activity (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            entity_id UUID NOT NULL,
            activity_type VARCHAR(50) NOT NULL,
            actor_id UUID,
            content TEXT,
            details JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_task_activity_entity ON task_activity(entity_id, created_at DESC)")
    op.execute("CREATE INDEX ix_task_activity_org ON task_activity(org_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_task_activity_org")
    op.execute("DROP INDEX IF EXISTS ix_task_activity_entity")
    op.execute("DROP TABLE IF EXISTS task_activity")
