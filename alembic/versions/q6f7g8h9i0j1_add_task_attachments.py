"""Add task_attachments table for file references on entities.

Revision ID: q6f7g8h9i0j1
Revises: p5e6f7g8h9i0
Create Date: 2026-04-11 00:06:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "q6f7g8h9i0j1"
down_revision = "p5e6f7g8h9i0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE task_attachments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            entity_id UUID NOT NULL,
            uploaded_by UUID REFERENCES org_members(id),
            filename VARCHAR(500) NOT NULL,
            file_size BIGINT,
            mime_type VARCHAR(200),
            storage_key VARCHAR(1000) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX ix_task_attachments_entity ON task_attachments(entity_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_task_attachments_entity")
    op.execute("DROP TABLE IF EXISTS task_attachments")
