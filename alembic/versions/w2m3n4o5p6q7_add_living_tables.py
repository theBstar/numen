"""Add Living tables (living_tasks, living_worktrees).

Revision ID: w2m3n4o5p6q7
Revises: v1l2m3n4o5p6
Create Date: 2026-05-02

This migration uses raw SQL to avoid SQLAlchemy's enum-type
auto-creation, which double-creates types when the same Enum is
both declared with .create() AND inlined into op.create_table.
"""

from alembic import op

# revision identifiers
revision = "w2m3n4o5p6q7"
down_revision = "v1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_task_status') THEN
                CREATE TYPE living_task_status AS ENUM
                    ('queued','spawning','running','done','failed','cancelled');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_worktree_status') THEN
                CREATE TYPE living_worktree_status AS ENUM
                    ('provisioning','ready','running','draining','archived');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'agent_runtime') THEN
                CREATE TYPE agent_runtime AS ENUM
                    ('claude_code','codex','cursor');
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS living_worktrees (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id),
            task_id UUID NULL,
            fs_path TEXT NOT NULL,
            branch_name VARCHAR(256) NOT NULL,
            process_pid INTEGER NULL,
            status living_worktree_status NOT NULL DEFAULT 'provisioning',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_worktrees_org "
        "ON living_worktrees (org_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_worktrees_task "
        "ON living_worktrees (task_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS living_tasks (
            id UUID PRIMARY KEY,
            org_id UUID NOT NULL REFERENCES organizations(id),
            name VARCHAR(512) NOT NULL,
            description TEXT NULL,
            runtime agent_runtime NOT NULL,
            status living_task_status NOT NULL DEFAULT 'queued',
            worktree_id UUID NULL REFERENCES living_worktrees(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ NULL,
            completed_at TIMESTAMPTZ NULL,
            context_fetch_count INTEGER NOT NULL DEFAULT 0,
            error_msg TEXT NULL
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_tasks_org_status "
        "ON living_tasks (org_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_tasks_org_created "
        "ON living_tasks (org_id, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_living_tasks_org_created;")
    op.execute("DROP INDEX IF EXISTS ix_living_tasks_org_status;")
    op.execute("DROP TABLE IF EXISTS living_tasks;")
    op.execute("DROP INDEX IF EXISTS ix_living_worktrees_task;")
    op.execute("DROP INDEX IF EXISTS ix_living_worktrees_org;")
    op.execute("DROP TABLE IF EXISTS living_worktrees;")
    op.execute("DROP TYPE IF EXISTS agent_runtime;")
    op.execute("DROP TYPE IF EXISTS living_worktree_status;")
    op.execute("DROP TYPE IF EXISTS living_task_status;")
