"""add living_event table + gdocs source type

Revision ID: x3o4p5q6r7s8
Revises: w2m3n4o5p6q7
Create Date: 2026-05-02
"""

from alembic import op

# revision identifiers
revision = "x3o4p5q6r7s8"
down_revision = "w2m3n4o5p6q7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the 'gdocs' source type. ALTER TYPE ... ADD VALUE cannot run
    #    inside a transaction block, so we drop into autocommit for it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE source_type ADD VALUE IF NOT EXISTS 'gdocs'")

    # 2. living_event table - append-only audit log for the Living spike.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS living_event (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES organizations(id),
            kind VARCHAR(64) NOT NULL,
            task_id UUID NOT NULL,
            worktree_id UUID,
            agent_id UUID NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            ts TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    # Tenant-scoped recency lookup (dashboards, replay).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_event_org_ts "
        "ON living_event(org_id, ts DESC)"
    )

    # Per-task chronological replay.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_event_task_ts "
        "ON living_event(task_id, ts ASC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_living_event_task_ts")
    op.execute("DROP INDEX IF EXISTS ix_living_event_org_ts")
    op.execute("DROP TABLE IF EXISTS living_event")
    # PostgreSQL does not support removing values from an enum without
    # recreating the type. Leaving the value in place is harmless.
