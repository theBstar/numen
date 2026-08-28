"""Add notifications table for member-facing alerts.

Revision ID: p5e6f7g8h9i0
Revises: o4d5e6f7g8h9
Create Date: 2026-04-11 00:05:00.000000

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "p5e6f7g8h9i0"
down_revision = "o4d5e6f7g8h9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            member_id UUID NOT NULL REFERENCES org_members(id),
            type VARCHAR(50) NOT NULL,
            entity_id UUID,
            actor_id UUID,
            title VARCHAR(500) NOT NULL,
            details JSONB DEFAULT '{}',
            read_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_notifications_member_unread ON notifications(org_id, member_id, read_at) WHERE read_at IS NULL"
    )
    op.execute("CREATE INDEX ix_notifications_member ON notifications(org_id, member_id, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_notifications_member")
    op.execute("DROP INDEX IF EXISTS ix_notifications_member_unread")
    op.execute("DROP TABLE IF EXISTS notifications")
