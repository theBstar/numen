"""Add living_pull_requests table for branch/PR/merge state tracking.

Revision ID: y4p5q6r7s8t9
Revises: x3o4p5q6r7s8
Create Date: 2026-05-03

The Mac app's Ship tab tracks which branch was pushed, which PR was opened
(if any), and how the change was merged back. Per-task; one row per task.

For local merges (no PR) ``provider='local'``, ``pr_number`` and ``pr_url``
remain NULL, and the row is created at merge-time. For PR-mode merges the row
appears the moment ``Push & Open PR`` is clicked, then mutates as the PR
state advances (open -> merged|closed) and the merge button is fired.

New event kinds (`branch_pushed`, `pr_state_changed`, `merge_completed`,
`merge_failed`) are written to the existing ``living_event`` table whose
``kind`` column is ``VARCHAR(64)`` -- no enum ALTER required.
"""

from alembic import op

# revision identifiers
revision = "y4p5q6r7s8t9"
down_revision = "x3o4p5q6r7s8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_pr_provider') THEN
                CREATE TYPE living_pr_provider AS ENUM ('github','local');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_pr_state') THEN
                CREATE TYPE living_pr_state AS ENUM
                    ('none','draft','open','merged','closed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_merge_state_status') THEN
                CREATE TYPE living_merge_state_status AS ENUM
                    ('unknown','clean','dirty','behind','blocked','has_hooks');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'living_merge_strategy') THEN
                CREATE TYPE living_merge_strategy AS ENUM ('merge','squash','rebase');
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS living_pull_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id UUID NOT NULL UNIQUE
                REFERENCES living_tasks(id) ON DELETE CASCADE,
            org_id UUID NOT NULL
                REFERENCES organizations(id) ON DELETE CASCADE,
            branch_name TEXT NOT NULL,
            base_branch TEXT NOT NULL,
            commit_head_sha TEXT NULL,
            provider living_pr_provider NOT NULL,
            pr_number INTEGER NULL,
            pr_url TEXT NULL,
            pr_state living_pr_state NOT NULL DEFAULT 'none',
            merge_state_status living_merge_state_status NOT NULL DEFAULT 'unknown',
            merge_strategy living_merge_strategy NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            merged_at TIMESTAMPTZ NULL
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_pull_requests_org_state "
        "ON living_pull_requests (org_id, pr_state);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_living_pull_requests_task "
        "ON living_pull_requests (task_id);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_living_pull_requests_task;")
    op.execute("DROP INDEX IF EXISTS ix_living_pull_requests_org_state;")
    op.execute("DROP TABLE IF EXISTS living_pull_requests;")
    op.execute("DROP TYPE IF EXISTS living_merge_strategy;")
    op.execute("DROP TYPE IF EXISTS living_merge_state_status;")
    op.execute("DROP TYPE IF EXISTS living_pr_state;")
    op.execute("DROP TYPE IF EXISTS living_pr_provider;")
